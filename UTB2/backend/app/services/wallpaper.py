import os
import io
import textwrap
from typing import List
from PIL import Image, ImageDraw, ImageFont

WIDTH = 1125
HEIGHT = 2436

BG_COLOR = "#000000"
TEXT_MAIN = "#FFFFFF"
TEXT_MUTED = "#8E8E93"
CARD_BG = "#1C1C1E"
CARD_BORDER = "#2C2C2E"
ACCENT_TIME = "#0A84FF"

FONT_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "Roboto-Regular.ttf")

def get_font(size: int):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except IOError:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
        except IOError:
            return ImageFont.load_default()

def wrap_text_by_width(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """Разбивает длинный текст по словами так, чтобы каждая строка влезла в max_width пикселей."""
    words = text.replace('\n', ' ').split()
    lines = []
    current_line = []

    for word in words:
        test_line = ' '.join(current_line + [word])
        if font.getlength(test_line) <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
                current_line = [word]
            else:
                # Если одно слово слишком длинное (длиннее всей доступной ширины)
                lines.append(word)
                current_line = []

    if current_line:
        lines.append(' '.join(current_line))

    return lines

def generate_schedule_wallpaper(day_name: str, lessons: List[object]) -> bytes:
    img = Image.new("RGB", (WIDTH, HEIGHT), color=BG_COLOR)
    draw = ImageDraw.Draw(img)

    count = len(lessons)

    # --- АДАПТИВНАЯ СЕТКА ПОД КОЛИЧЕСТВО ПАР (Сохранена полностью) ---
    if count <= 4:
        card_height = 190
        gap = 26
        title_sz, time_sz, room_sz = 44, 36, 32
    elif count <= 6:
        card_height = 150
        gap = 20
        title_sz, time_sz, room_sz = 36, 30, 26
    elif count <= 8:
        card_height = 120
        gap = 14
        title_sz, time_sz, room_sz = 30, 24, 22
    else:
        card_height = 95
        gap = 10
        title_sz, time_sz, room_sz = 24, 20, 18

    font_header = get_font(52)
    font_title = get_font(title_sz)
    font_time = get_font(time_sz)
    font_room = get_font(room_sz)

    # Отступ сверху 650px — под часы iOS
    current_y = 650
    padding_x = 75
    card_width = WIDTH - (padding_x * 2)

    # Заголовок
    draw.text((padding_x, current_y), day_name.upper(), fill=TEXT_MUTED, font=font_header)
    current_y += 90

    if not lessons:
        draw.text((padding_x, current_y + 40), "Занятий нет! Отдыхаем.", fill=TEXT_MAIN, font=font_title)
    else:
        for lesson in lessons:
            x0, y0 = padding_x, current_y
            x1, y1 = padding_x + card_width, current_y + card_height

            # Карточка
            draw.rounded_rectangle(
                [x0, y0, x1, y1],
                radius=26,
                fill=CARD_BG,
                outline=CARD_BORDER,
                width=2
            )

            # Время
            time_str = getattr(lesson, 'time', '')
            time_x = x0 + 32
            time_y = y0 + (card_height // 2) - (time_sz // 2) - 2
            draw.text((time_x, time_y), time_str, fill=ACCENT_TIME, font=font_time)

            # --- ПРЕДМЕТ С ПЕРЕНОСОМ НА НОВУЮ СТРОКУ ---
            subject_x = time_x + 210
            max_text_width = x1 - subject_x - 30  # Доступная ширина внутри карточки

            subject_raw = str(getattr(lesson, 'subject', ''))
            lines = wrap_text_by_width(subject_raw, font_title, max_text_width)

            # Вычисляем общую высоту всего текстового блока (предмет + аудитория)
            room_val = getattr(lesson, 'room', None)
            line_spacing = 6
            title_line_height = title_sz + 2

            # Ограничиваем максимальное число строк в зависимости от высоты карточки
            max_lines = 2 if card_height >= 150 else 1
            lines = lines[:max_lines]

            total_text_height = len(lines) * title_line_height + (len(lines) - 1) * line_spacing
            if room_val:
                total_text_height += room_sz + line_spacing

            # Выравниваем весь блок текста ровно по центру карточки по вертикали
            start_text_y = y0 + (card_height - total_text_height) // 2

            # Рисуем строки предмета
            for i, line in enumerate(lines):
                line_y = start_text_y + i * (title_line_height + line_spacing)
                draw.text((subject_x, line_y), line, fill=TEXT_MAIN, font=font_title)

            # Аудитория
            if room_val:
                room_str = f"ауд. {room_val}"
                room_y = start_text_y + len(lines) * (title_line_height + line_spacing)
                draw.text((subject_x, room_y), room_str, fill=TEXT_MUTED, font=font_room)

            current_y += card_height + gap

    output = io.BytesIO()
    img.save(output, format="PNG", optimize=True)
    return output.getvalue()
