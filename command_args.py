"""A-SOUL member names and command filters from LEN5010/astrbot_plugin_dynamic_asoul."""
import re
from datetime import date

FANART_CHARACTER_OPTIONS = ("贝拉", "嘉然", "乃琳", "心宜&思诺")

MEMBER_NAME_ALIASES = {'嘉然': '嘉然', '然然': '嘉然', 'diana': '嘉然', 'Diana': '嘉然', '贝拉': '贝拉', '拉姐': '贝拉', '队长': '贝拉', 'bella': '贝拉', 'Bella': '贝拉', '乃琳': '乃琳', '奶琳': '乃琳', 'eileen': '乃琳', 'Eileen': '乃琳', '向晚': '向晚', '晚晚': '向晚', 'ava': '向晚', 'Ava': '向晚', '珈乐': '珈乐', 'carol': '珈乐', 'Carol': '珈乐', '心宜': '心宜', 'fiona': '心宜', 'Fiona': '心宜', '思诺': '思诺', 'gladys': '思诺', 'Gladys': '思诺', '心宜&思诺': '心宜&思诺', '心宜思诺': '心宜&思诺', '思诺心宜': '心宜&思诺'}

FANART_CATEGORY_ALIASES = {'普通': '普通', '物料': '物料', '手书': '手书·动画', '动画': '手书·动画', '手书·动画': '手书·动画', '手书动画': '手书·动画', '剪辑': '剪辑·AMV', 'amv': '剪辑·AMV', 'AMV': '剪辑·AMV', '剪辑·AMV': '剪辑·AMV', '剪辑amv': '剪辑·AMV', '3d': 'MMD·3D', '3D': 'MMD·3D', 'mmd': 'MMD·3D', 'MMD': 'MMD·3D', 'MMD·3D': 'MMD·3D', '其他视频': '其他视频', '视频': 'all'}

FANART_CONTENT_TYPE_ALIASES = {'图': 'image', '图片': 'image', '插画': 'image', '画': 'image', 'image': 'image', '视频': 'video', 'video': 'video', '文本': 'text', '文字': 'text', 'text': 'text', '其他': 'other', 'other': 'other', '全部': 'all', 'all': 'all'}

def parse_fanart_args(args: tuple[str, ...], command_name: str = "") -> dict:
    """解析随机二创指令中的角色、分类、类型参数"""
    result = {
        "character": None,
        "category": None,
        "content_type": None,
    }

    if "图片" in command_name:
        result["content_type"] = "image"
    elif "视频" in command_name:
        result["content_type"] = "video"

    for raw_arg in args:
        arg = raw_arg.strip()
        if not arg:
            continue

        # 检查是否为角色
        matched_char = None
        for char_opt in FANART_CHARACTER_OPTIONS:
            if char_opt in arg or arg in char_opt:
                matched_char = char_opt
                break
        if not matched_char and arg in MEMBER_NAME_ALIASES:
            canonical = MEMBER_NAME_ALIASES[arg]
            if canonical in FANART_CHARACTER_OPTIONS:
                matched_char = canonical
        if matched_char:
            result["character"] = matched_char
            continue

        # 检查是否为内容类型（图片/视频/文本）
        if arg in FANART_CONTENT_TYPE_ALIASES:
            result["content_type"] = FANART_CONTENT_TYPE_ALIASES[arg]
            continue

        # 检查是否为分类（普通/手书/剪辑/3D）
        if arg in FANART_CATEGORY_ALIASES:
            cat = FANART_CATEGORY_ALIASES[arg]
            if cat == "all":
                result["content_type"] = "video"
            else:
                result["category"] = cat
            continue

    return result

def month_day(text: str) -> str:
    match = re.fullmatch(r"(\d{1,2})[-/月.](\d{1,2})日?", text.strip())
    if match is None:
        raise ValueError('日期写成 08-16、8/16 或 8月16日')
    day = date(2000, int(match[1]), int(match[2]))
    return day.strftime('%m-%d')
