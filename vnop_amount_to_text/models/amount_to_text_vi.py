# -*- coding: utf-8 -*-


ONES = [
    "", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín",
]

GROUP_NAMES = [
    "", "nghìn", "triệu", "tỷ", "nghìn tỷ", "triệu tỷ",
]


def _read_three_digits(hundreds, tens, ones, has_higher_group):
    """Đọc nhóm 3 chữ số, trả về list các từ."""
    parts = []

    if hundreds:
        parts.append(ONES[hundreds])
        parts.append("trăm")
    elif has_higher_group and (tens or ones):
        parts.append("không")
        parts.append("trăm")

    if tens > 1:
        parts.append(ONES[tens])
        parts.append("mươi")
    elif tens == 1:
        parts.append("mười")

    if ones == 1:
        if tens and tens >= 2:
            parts.append("mốt")
        elif not tens and (hundreds or has_higher_group):
            parts.append("linh")
            parts.append("một")
        else:
            parts.append("một")
    elif ones == 4 and tens and tens >= 2:
        parts.append("tư")
    elif ones == 5 and tens and tens >= 1:
        parts.append("lăm")
    elif ones:
        if tens == 0 and (hundreds or has_higher_group):
            parts.append("linh")
        parts.append(ONES[ones])

    return parts


def _split_groups(number):
    """Tách số thành các nhóm 3 chữ số từ phải sang trái."""
    groups = []
    while number > 0:
        groups.append(number % 1000)
        number //= 1000
    return groups


def amount_to_text_vi(amount, currency_name="đồng"):
    """Chuyển số tiền thành chữ tiếng Việt.

    Args:
        amount: Số tiền (float hoặc int).
        currency_name: Tên đơn vị tiền tệ (mặc định "đồng").

    Returns:
        Chuỗi chữ tiếng Việt, viết hoa chữ cái đầu.
        VD: "Một triệu năm trăm nghìn đồng"
    """
    if amount is None:
        return ""

    amount = round(amount)

    if amount == 0:
        return "Không %s" % currency_name

    negative = amount < 0
    amount = abs(amount)

    groups = _split_groups(amount)
    words = []

    for i in range(len(groups) - 1, -1, -1):
        group_val = groups[i]
        if group_val == 0:
            continue

        hundreds = group_val // 100
        tens = (group_val % 100) // 10
        ones = group_val % 10

        has_higher = i < len(groups) - 1
        group_words = _read_three_digits(hundreds, tens, ones, has_higher)

        if group_words:
            words.extend(group_words)
            if i < len(GROUP_NAMES):
                if GROUP_NAMES[i]:
                    words.append(GROUP_NAMES[i])

    result = " ".join(words)

    if negative:
        result = "âm " + result

    result = result[0].upper() + result[1:]
    result += " " + currency_name

    return result
