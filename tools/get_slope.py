from decimal import Decimal
from typing import Any, List, Optional, Tuple
from tools.belt_utils import get_belt_y_positions, get_texts_in_range
from tools.controller import SLOPE_TITLE_CANDIDATES

def init(msp: Any, text_layer: str) -> List[Tuple[str, Tuple[float, float], float]]:
    """
    「勾配」帯を検出し、その下端 `min_y` より上（+∞ まで）の範囲にある TEXT を取得する初期化ヘルパ。

    処理手順:
        1) `get_belt_y_positions(msp, text_layer, "勾配", "勾", "配")` により帯の上下端を推定。
        2) 下端 `min_y` より上の TEXT を `get_texts_in_range` で抽出。

    Args:
        msp (Any): ezdxf の Modelspace。
        text_layer (str): 「勾配」帯のテキストが配置されているレイヤー名。

    Returns:
        List[Tuple[str, Tuple[float, float], float]]:
            `(text, (x, y), rotation_deg)` のタプルのリスト。
            範囲は `[min_y, +∞)`。
    """

    min_y = None

    for label, c1, c2 in SLOPE_TITLE_CANDIDATES:
        min_y, _ = get_belt_y_positions(msp, text_layer, label, c1, c2)
        if min_y is not None:
            break

    # min_y より上（〜 +∞）の範囲にあるテキストを取得
    return get_texts_in_range(msp, text_layer, min_y, float("inf"))


def _parse_slope_value(text: str) -> Tuple[Optional[Decimal], bool]:
    """
    勾配テキストから数値と「% 表記であるか」のフラグを抽出して返す。
        - `'i='` または `'I='` を含む文字列のみを対象とする。
        - `%` または `％` が含まれている場合はパーセント表記とみなし、記号を除去して数値化。
        - パーセント表記でない場合（例: `i=3.5`）は `%` 単位へ換算（×100）して返す。

    Args:
        text (str): 勾配テキスト（例: `"i=3.5"`, `"I=3.5%"`, `"i=3.5％"`）。

    Returns:
        Tuple[Optional[Decimal], bool]:
            `(value, is_percent)` のタプル。
            - `value`: 数値化した勾配値（`Decimal`）。対象外/解析失敗時は `None`。
            - `is_percent`: 入力がパーセント表記であった場合 True、数値のみだった場合 False。

    Notes:
        - `'i='` / `'I='` を除去後に数値化し、未パーセントの場合は最終的に `%` 単位へ正規化します。
        - 数値化に失敗した場合は `(None, False)` を返します。
    """

    if "i=" not in text and "I=" not in text:
        return None, False

    # "i=" / "I=" を除去
    value_str = text.replace("i=", "").replace("I=", "").strip()

    # ％表記かどうか判定＆記号除去
    is_percent = ("%" in text) or ("％" in text)
    if is_percent:
        value_str = value_str.replace("%", "").replace("％", "").strip()

    try:
        value = Decimal(value_str)
    except Exception:
        return None, False

    # ％表記でない場合は % 単位に変換（×100）
    if not is_percent:
        value *= 100

    return value, is_percent


def get_slope_values(
    msp: Any,
    text_layer: str,
    check_rotation: bool,
) -> List[Tuple[Decimal, Tuple[float, float], float]]:
    """
    「勾配」帯の下端より上にある `'i=' / 'I='` テキストを抽出し、勾配値を `%` 単位の Decimal として返す。
        - `%` 表記でなければ `%` 単位に換算（×100）。
        - `check_rotation=True` の場合、TEXT 回転角度が `(270, 360)` の範囲なら負符号を付与（× -1）。
        - 返却リストは x 座標で昇順ソート。

    Args:
        msp (Any)            : ezdxf の Modelspace。
        text_layer (str)     : 勾配テキストが配置されているレイヤー名。
        check_rotation (bool): 回転角度に応じて符号反転を行うか。True で `(270, 360)` を負とする。

    Returns:
        List[Tuple[Decimal, Tuple[float, float], float]]:
            勾配値のリスト。各要素は `(value: Decimal, position: (x, y), rotation_deg)`。

    Notes:
        - 帯検出と範囲抽出は `init()` に依存します。
        - 符号反転の角度範囲は既存仕様 `(270, 360)` を踏襲しています。
    """
    texts_above_min_y = init(msp, text_layer)

    slope_values: List[Tuple[Decimal, Tuple[float, float], float]] = []
    for text, position, rotation in texts_above_min_y:
        value, _ = _parse_slope_value(text)
        if value is None:
            continue

        # 回転角度の確認が必要な場合のみ符号反転
        if check_rotation and (270 < rotation < 360):
            value *= -1

        slope_values.append((value, position, rotation))

    # x 座標で昇順ソート
    slope_values.sort(key=lambda item: item[1][0])

    return slope_values


def get_max(msp: Any, text_layer: str):
    """
    勾配帯内の `'i=●●' / 'I=●●'` のうち、最も大きい値（% 単位）を返す。
        - 回転角度は無視（`check_rotation=False`）。
        - 勾配が 1 つも存在しない場合は `"-"` を返す。

    Args:
        msp (Any): ezdxf の Modelspace。
        text_layer (str): 勾配テキストが配置されているレイヤー名。

    Returns:
        Decimal | str:
            - 成功時: 最大の勾配値（`Decimal`、% 単位）。
            - 失敗時: `"-"`。
    """

    slope_values = get_slope_values(msp, text_layer, check_rotation=False)
    if slope_values:
        return max(v for v, _, _ in slope_values)
    return "-"