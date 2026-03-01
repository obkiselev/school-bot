"""Registration flow handlers — авторизация через mos.ru + SMS."""
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from states.registration import RegistrationStates
from database.crud import create_user, add_child, create_default_notifications, log_activity
from mesh_api.auth import MeshAuth, _pending_auth, clear_pending_auth
from mesh_api.models import student_from_octodiary
from mesh_api.exceptions import AuthenticationError, NetworkError, MeshAPIError

logger = logging.getLogger(__name__)

router = Router()


@router.message(RegistrationStates.waiting_for_mesh_login)
async def process_mesh_login(message: Message, state: FSMContext):
    """Process МЭШ login input."""
    login = message.text.strip()

    # Basic validation
    if not login or len(login) < 3:
        await message.answer("Некорректный логин. Попробуйте еще раз:")
        return

    # Save login to FSM context
    await state.update_data(mesh_login=login)

    await message.answer(
        "Логин сохранен.\n\n"
        "Теперь введите ваш пароль от mos.ru:\n\n"
        "<i>Пароль будет зашифрован и надежно сохранен.</i>",
        parse_mode="HTML"
    )

    # Move to next state
    await state.set_state(RegistrationStates.waiting_for_mesh_password)


@router.message(RegistrationStates.waiting_for_mesh_password)
async def process_mesh_password(message: Message, state: FSMContext):
    """Process mos.ru password and start authentication."""
    password = message.text.strip()

    # Delete message with password for security
    try:
        await message.delete()
    except Exception:
        pass

    # Basic validation
    if not password or len(password) < 3:
        await message.answer("Некорректный пароль. Попробуйте еще раз:")
        return

    # Get login from FSM
    data = await state.get_data()
    login = data.get("mesh_login")

    if not login:
        await message.answer("Ошибка: логин не найден. Начните сначала с /start")
        await state.clear()
        return

    # Show verification message
    verify_msg = await message.answer(
        "Подключаюсь к серверу МЭШ...\n"
        "Это может занять несколько секунд."
    )

    # Try to authenticate
    user_id = message.from_user.id
    auth = MeshAuth()

    async def on_retry(attempt: int, total: int) -> None:
        await verify_msg.edit_text(
            f"Сервер не ответил (попытка {attempt}/{total}). Пробую ещё раз...\n"
            "Подождите ещё ~30 секунд."
        )

    try:
        result = await auth.start_login(login, password, on_retry=on_retry)

        if result["status"] == "sms_required":
            # Сохраняем сессию авторизации в памяти (не в FSM — объект несериализуемый)
            _pending_auth[user_id] = auth

            await state.update_data(mesh_password=password)
            await state.set_state(RegistrationStates.waiting_for_sms_code)

            contact = result.get("contact", "ваш телефон")
            ttl = result.get("ttl", 300)
            minutes = ttl // 60

            await verify_msg.edit_text(
                f"На номер <b>{contact}</b> отправлен SMS-код.\n\n"
                f"Введите код из SMS (действует {minutes} мин.):",
                parse_mode="HTML"
            )
            return

        # Прямой вход без SMS (редко)
        await _process_auth_success(message, state, verify_msg, result, login, password)

    except AuthenticationError as e:
        await verify_msg.edit_text(
            f"Ошибка входа: {e}\n\n"
            "Проверьте правильность логина и пароля, затем начните заново: /start"
        )
        await state.clear()
        clear_pending_auth(user_id)

    except (NetworkError, MeshAPIError) as e:
        await verify_msg.edit_text(
            f"Ошибка сети: {e}\n\n"
            "Попробуйте позже: /start"
        )
        await state.clear()
        clear_pending_auth(user_id)


@router.message(RegistrationStates.waiting_for_sms_code)
async def process_sms_code(message: Message, state: FSMContext):
    """Process SMS code from mos.ru."""
    code = message.text.strip()
    user_id = message.from_user.id

    # Validate code format
    if not code or not code.isdigit() or len(code) < 4:
        await message.answer("Введите корректный SMS-код (только цифры):")
        return

    # Get pending auth session
    auth = _pending_auth.get(user_id)
    if not auth:
        await message.answer(
            "Сессия авторизации истекла. Начните заново: /start"
        )
        await state.clear()
        return

    verify_msg = await message.answer("Проверяю SMS-код...")

    data = await state.get_data()
    login = data.get("mesh_login")
    password = data.get("mesh_password")

    try:
        result = await auth.verify_sms(code)
        clear_pending_auth(user_id)
        await _process_auth_success(message, state, verify_msg, result, login, password)

    except AuthenticationError as e:
        error_msg = str(e)
        if "заново" in error_msg.lower() or "истёк" in error_msg.lower():
            # Код истёк или исчерпаны попытки — нужно начать сначала
            await verify_msg.edit_text(f"{e}")
            await state.clear()
            clear_pending_auth(user_id)
        else:
            # Неверный код — можно попробовать ещё раз
            await verify_msg.edit_text(
                f"{e}\n\n"
                "Попробуйте ввести код ещё раз:"
            )

    except (NetworkError, MeshAPIError) as e:
        # Сетевая ошибка — сессия и SMS-код ещё действительны.
        # Не сбрасываем FSM и _pending_auth: пользователь может повторить ввод того же кода.
        await verify_msg.edit_text(
            f"Ошибка сети: {e}\n\n"
            "Попробуйте ввести тот же код ещё раз."
        )


async def _process_auth_success(
    message: Message,
    state: FSMContext,
    verify_msg: Message,
    auth_result: dict,
    login: str,
    password: str,
):
    """Обработка успешной авторизации — показ списка детей."""
    token = auth_result["token"]
    children_data = auth_result.get("children", [])

    if not children_data:
        await verify_msg.edit_text(
            "В профиле не найдено ни одного ребенка.\n\n"
            "Убедитесь, что ваш аккаунт привязан к профилю ученика, "
            "и попробуйте снова: /start"
        )
        await state.clear()
        return

    # Конвертируем OctoDiary children в наши Student объекты
    students = [student_from_octodiary(child) for child in children_data]

    # Save to FSM
    await state.update_data(
        mesh_password=password,
        mesh_token=token,
        mesh_profile_id=auth_result.get("profile_id"),
        mesh_role=auth_result.get("mes_role"),
        mesh_refresh_token=auth_result.get("refresh_token"),
        mesh_client_id=auth_result.get("client_id"),
        mesh_client_secret=auth_result.get("client_secret"),
        students=students,
    )

    await verify_msg.edit_text(
        f"Вход выполнен успешно!\n\n"
        f"Найдено детей: {len(students)}"
    )

    # Show children selection
    await show_children_selection(message, students, state)


async def show_children_selection(message: Message, students, state: FSMContext):
    """Show inline keyboard to select children."""
    keyboard_buttons = []

    for student in students:
        full_name = f"{student.last_name} {student.first_name}"
        if student.class_name:
            full_name += f" ({student.class_name})"

        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"  {full_name}",
                callback_data=f"select_child_{student.student_id}"
            )
        ])

    keyboard_buttons.append([
        InlineKeyboardButton(
            text="Подтвердить выбор",
            callback_data="confirm_children_selection"
        )
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    await message.answer(
        "Выберите детей, для которых вы хотите получать информацию:\n\n"
        "<i>Нажмите на имя, чтобы выбрать/отменить выбор.\n"
        "Когда закончите, нажмите \"Подтвердить выбор\".</i>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

    # Initialize selected children (select all by default)
    await state.update_data(
        selected_student_ids=[s.student_id for s in students]
    )
    await state.set_state(RegistrationStates.selecting_children)


@router.callback_query(
    RegistrationStates.selecting_children,
    F.data.startswith("select_child_")
)
async def toggle_child_selection(callback: CallbackQuery, state: FSMContext):
    """Toggle child selection."""
    student_id = int(callback.data.split("_")[-1])

    data = await state.get_data()
    selected_ids = data.get("selected_student_ids", [])

    # Toggle selection
    if student_id in selected_ids:
        selected_ids.remove(student_id)
    else:
        selected_ids.append(student_id)

    await state.update_data(selected_student_ids=selected_ids)

    # Update keyboard to reflect selection
    students = data.get("students", [])
    keyboard_buttons = []

    for student in students:
        full_name = f"{student.last_name} {student.first_name}"
        if student.class_name:
            full_name += f" ({student.class_name})"

        prefix = "  " if student.student_id in selected_ids else "  "

        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"{prefix} {full_name}",
                callback_data=f"select_child_{student.student_id}"
            )
        ])

    keyboard_buttons.append([
        InlineKeyboardButton(
            text="Подтвердить выбор",
            callback_data="confirm_children_selection"
        )
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()


@router.callback_query(
    RegistrationStates.selecting_children,
    F.data == "confirm_children_selection"
)
async def confirm_children_selection(callback: CallbackQuery, state: FSMContext):
    """Confirm selection and save to database."""
    data = await state.get_data()
    selected_ids = data.get("selected_student_ids", [])

    if not selected_ids:
        await callback.answer("Выберите хотя бы одного ребенка!", show_alert=True)
        return

    await callback.message.edit_text(
        "Сохраняю данные...\n"
        "Пожалуйста, подождите."
    )

    # Save user and children to database
    try:
        user_id = callback.from_user.id
        login = data.get("mesh_login")
        password = data.get("mesh_password")
        token = data.get("mesh_token")
        students = data.get("students", [])

        # Create user with OAuth fields
        await create_user(
            user_id=user_id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
            mesh_login=login,
            mesh_password=password,
            mesh_token=token,
            mesh_refresh_token=data.get("mesh_refresh_token"),
            mesh_client_id=data.get("mesh_client_id"),
            mesh_client_secret=data.get("mesh_client_secret"),
            mesh_profile_id=data.get("mesh_profile_id"),
            mesh_role=data.get("mesh_role"),
        )

        # Add selected children
        added_count = 0
        for student in students:
            if student.student_id in selected_ids:
                child_id = await add_child(
                    user_id=user_id,
                    student_id=student.student_id,
                    first_name=student.first_name,
                    last_name=student.last_name,
                    middle_name=student.middle_name,
                    class_name=student.class_name,
                    school_name=student.school_name,
                    person_id=student.person_id,
                    class_unit_id=student.class_unit_id,
                )

                # Create default notifications for this child
                await create_default_notifications(user_id, child_id)

                added_count += 1

        # Log activity
        await log_activity(user_id, "registration", f"Added {added_count} children")

        # Clear FSM
        await state.clear()

        await callback.message.edit_text(
            f"Регистрация завершена успешно!\n\n"
            f"Добавлено детей: {added_count}\n\n"
            "Доступные команды:\n"
            "/raspisanie - Расписание уроков\n"
            "/ocenki - Оценки\n"
            "/dz - Домашние задания\n"
            "/profile - Мой профиль\n"
            "/settings - Настройки уведомлений\n"
            "/help - Справка\n\n"
            "Уведомления включены по умолчанию:\n"
            "  Оценки - каждый день в 18:00\n"
            "  Домашние задания - каждый день в 19:00\n\n"
            "Вы можете изменить настройки в /settings"
        )

    except Exception as e:
        logger.error("Ошибка при сохранении регистрации: %s", e)
        await callback.message.edit_text(
            f"Ошибка при сохранении: {e}\n\n"
            "Попробуйте начать заново: /start"
        )
        await state.clear()

    await callback.answer()
