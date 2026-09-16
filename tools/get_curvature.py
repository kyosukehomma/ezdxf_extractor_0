import math
from decimal import Decimal
from typing import Optional, List, Tuple, Any, Union, Iterable, Callable
from tools.belt_utils import get_belt_y_positions, get_texts_in_range
from tools.controller import (
    CURVATURE_TITLE_CANDIDATES,
    CURVATURE_R_PREFIXES,
    CURVATURE_A_PREFIXES,
    CURVATURE_L_PREFIXES,
    X_MERGE_THRESHOLD,
)

# ----------------------------
# Type aliases
# ----------------------------
"""
このファイル内で扱うタプルの形を明確にするための型エイリアスです。
3要素タプル（値, 座標, 属性）と 4要素タプル（値, 座標, 属性, 方向）を定義しておき、
関数引数では両方を受け取れるよう Union 型を用意します。

- value: 数値 or 文字列（例: '∞' など）。float へ変換可能な場合があります。
- (x, y): CAD 図面上の座標（float）
- attribute: 文字列で属性を表します（例: 'R', 'A', 'L'）
- direction: 文字列で方向を表します（例: 'straight', 'right', 'left'）
"""
# (value, (x, y), attribute)
Element = Tuple[Any, Tuple[float, float], str]

# (value, (x, y), attribute, direction)
ElementWithDir = Tuple[Any, Tuple[float, float], str, str]

# 上記2種のいずれかを受け取れるようにするための合成型
TextItem = Union[Element, ElementWithDir]


# ----------------------------
# Text extraction
# ----------------------------
def get_texts_replaced_prefix(
    texts_in_range: Iterable[Tuple[str, Tuple[float, float], float]],
    target_prefixes: List[str],
    attribute_alias: Optional[str] = None,
) -> List[Tuple[Any, Tuple[float, float], str]]:
    """
    テキストの先頭接頭辞（複数候補）を 1 回だけ除去し、その値と座標と属性をタプルにして返す。
        - `text.startswith(tuple(target_prefixes))` に一致した接頭辞を 1 回だけ除去。
        - 値は `float` へ変換（"∞" は `float("inf")`）。変換失敗はスキップ。
        - 属性は、`attribute_alias` 指定時はその値を、未指定時は接頭辞から `"="` を除いて使用。

    Args:
        texts_in_range (Iterable[Tuple[str, Tuple[float, float], float]]):
            `(text, (x, y), rotation_deg)` のタプルの列（`get_texts_in_range` の出力を想定）。
        target_prefixes (List[str]): 接頭辞の候補（例: `["R="]`, `["A="]`,
            `["L=", "L1=", "LC=", "L2="]` など）。
        attribute_alias (Optional[str]): 属性を接頭辞に依存せず、この値に正規化したい場合に指定。
            例: `target_prefixes=["L=", "LC="]` に対して `attribute_alias="L"`。

    Returns:
        List[Tuple[Any, Tuple[float, float], str]]:
            `[(value: float|inf, (x, y), attribute: str), ...]` のリスト。
    """

    processed: List[Tuple[Any, Tuple[float, float], str]] = []
    prefix_tuple = tuple(target_prefixes)

    for text, position, _ in texts_in_range:
        if not isinstance(text, str):
            continue

        if text.startswith(prefix_tuple):
            # 実際にマッチした接頭辞
            matched_prefix = next(p for p in target_prefixes if text.startswith(p))

            # 接頭辞を1回だけ除去
            processed_text = text.replace(matched_prefix, "", 1).strip()

            # 属性の決定：alias が指定されていればそれを使う。なければ従来通り。
            attribute = attribute_alias if attribute_alias is not None else matched_prefix.replace("=", "")

            if processed_text == "∞":
                processed.append((float("inf"), position, attribute))
            else:
                try:
                    val = float(processed_text)
                except ValueError:
                    continue
                processed.append((val, position, attribute))

    return processed


# ----------------------------
# Utilities
# ----------------------------
def combine_and_sort_texts(
    *lists: Iterable[Element],
    key: Callable[[Element], float] = lambda item: item[1][0]
) -> List[Element]:
    """
    複数の `Element` リストを結合し、指定キーでソートして返す。

    Args:
        *lists (Iterable[Element])      : 結合対象の `Element` リスト（可変長引数）。
        key (Callable[[Element], float]): ソートキー関数。デフォルトは x 座標（`item[1][0]`）。

    Returns:
        List[Element]: 結合・ソート後の `Element` リスト。
    """
    combined: List[Element] = []
    for lst in lists:
        combined.extend(lst)
    combined.sort(key=key)
    return combined


def unify_close_x_coordinates(
    combined_texts: List[Element],
    threshold: float = X_MERGE_THRESHOLD
) -> List[Element]:
    """
    隣接する要素の x 差が閾値以下の場合、両者の x を平均値で統一する。

    対象:
        - 2 件のペアを順次処理（連続群への拡張は既存仕様維持のため未対応）。

    Args:
        combined_texts (List[Element]): `(value, (x, y), attr)` のリスト（x 昇順想定）。
        threshold (float): x 差の許容閾値。デフォルト 5000.0。

    Returns:
        List[Element]: x 統一後の `Element` リスト（新しいリストを返す）。

    Notes:
        - 内部で隣接ペアを見て、差分が `<= threshold` の場合のみ統一します。
        - y・attr はそのまま維持し、x のみ平均値に置換します。
    """

    if len(combined_texts) < 2:
        return combined_texts[:]

    unified = combined_texts[:]
    i = 0
    while i < len(unified) - 1:
        now_x = float(unified[i][1][0])
        next_x = float(unified[i + 1][1][0])
        if abs(now_x - next_x) <= threshold:
            new_x = (now_x + next_x) / 2.0
            unified[i] = (unified[i][0], (new_x, unified[i][1][1]), unified[i][2])
            unified[i + 1] = (unified[i + 1][0], (new_x, unified[i + 1][1][1]), unified[i + 1][2])
            i += 2
        else:
            i += 1
    return unified


def split_by_attribute(
    texts: List[TextItem],
    attribute: str,
    is_else: Optional[bool] = False
) -> List[TextItem]:
    """
    属性一致/不一致で `TextItem` をフィルタする。

    Args:
        texts (List[TextItem])  : `(value, (x, y), attr[, direction])` のリスト。
        attribute (str)         : フィルタ対象の属性（例: `"R"`, `"A"`, `"L"`）。
        is_else (Optional[bool]): True の場合は「不一致」を返し、False の場合は「一致」を返す。

    Returns:
        List[TextItem]: フィルタ後の `TextItem` リスト。
    """

    if is_else:
        return [t for t in texts if t[2] != attribute]
    return [t for t in texts if t[2] == attribute]


# ----------------------------
# Direction annotation
# ----------------------------
def add_element_direction(
    texts_unified: List[Element],
    min_y: float,
    max_y: float,
    center_y: float
) -> List[ElementWithDir]:

    """
    曲がる方向（right/left/straight）を判定し、各要素に方向属性を付与して返す。

    判定ルール（既存仕様踏襲）:
        1) L と同じ x の {A or R} を選び、R=∞ なら `straight`。
        2) それ以外は (L.y + {A/R}.y)/2 と `center_y` を比較する:
            - 上    → `right`
            - 下    → `left`
            - 一致  → `straight`。

    Args:
        texts_unified (List[Element]): x 統一済みの `(value, (x, y), attr)` のリスト。
        min_y (float)   : 帯の下端 Y。
        max_y (float)   : 帯の上端 Y。
        center_y (float): 帯の中央 Y（`(min_y + max_y)/2`）。

    Returns:
        List[ElementWithDir]: `(value, (x, y), attr, direction)` を付与したリスト。

    Notes:
        - "∞" / "inf" / "INF" は曲率 R の無限として扱い、`straight`。
        - 値は可能なら `float` に正規化して格納（失敗時は原値のまま）。
        - L と同じ x に {A/R} が無い場合はその L はスキップ（判定不可）。
    """

    added: List[ElementWithDir] = []

    # L と L以外で分離
    unified_is_L: List[Element] = split_by_attribute(texts_unified, "L")
    unified_not_L: List[Element] = split_by_attribute(texts_unified, "L", True)

    # 同じ x の {A or R} 検索を効率化（x -> [not_L elements]）
    not_L_by_x = {}
    for val, (x, y), attr in unified_not_L:
        not_L_by_x.setdefault(x, []).append((val, (x, y), attr))

    def choose_partner_for_x(x_L: float) -> Optional[Element]:
        # A を優先、なければ R
        candidates = not_L_by_x.get(x_L, [])
        partner_A = next((c for c in candidates if c[2] == "A"), None)
        if partner_A:
            return partner_A
        partner_R = next((c for c in candidates if c[2] == "R"), None)
        return partner_R

    def is_R_infinite(text_value: Any, attr: str) -> bool:
        if attr != "R":
            return False
        try:
            return math.isinf(float(text_value))
        except Exception:
            s = str(text_value).strip()
            return s in {"∞", "inf", "INF"}

    def to_float_if_possible(v: Any) -> Any:
        try:
            return float(v)
        except Exception:
            return v

    for val_L, (x_L, y_L), attr_L in unified_is_L:
        partner = choose_partner_for_x(x_L)
        if partner is None:
            # 同じ x 上に {A/R} が存在しない場合は判定不可のためスキップ
            continue

        val_NR, (x_NR, y_NR), attr_NR = partner
        if x_L != x_NR:
            # 念のため一致確認
            continue

        if is_R_infinite(val_NR, attr_NR):
            direction = "straight"
        else:
            y_mid = (y_L + y_NR) / 2.0
            if y_mid > center_y:
                direction = "right"
            elif y_mid < center_y:
                direction = "left"
            else:
                direction = "straight"

        added.append((to_float_if_possible(val_L), (x_L, y_L), attr_L, direction))
        added.append((to_float_if_possible(val_NR), (x_NR, y_NR), attr_NR, direction))

    return added


def split_by_direction(
    texts_dir: List[ElementWithDir]
) -> Tuple[List[ElementWithDir], List[ElementWithDir]]:
    """
    `direction` が `"right"` と `"left"` の 2 種に分割する（1 パス）。

    Args:
        texts_dir (List[ElementWithDir]):
            `(value, (x, y), attr, direction)` のリスト。

    Returns:
        Tuple[List[ElementWithDir], List[ElementWithDir]]:
            `(right_list, left_list)` の 2 要素タプル。
    """

    right, left = [], []
    for el in texts_dir:
        dir_ = el[3]
        if dir_ == "right":
            right.append(el)
        elif dir_ == "left":
            left.append(el)
    return right, left


# ----------------------------
# Duplicate deletion
# ----------------------------
def delete_the_same_curves(
    R_texts_added: List[ElementWithDir],
    A_texts_added: List[ElementWithDir],
    L_texts_added: List[ElementWithDir],
    is_multi_layouts: bool,
    is_R_plus_A_equal_L: bool
) -> Tuple[
        List[ElementWithDir],
        List[ElementWithDir],
        List[ElementWithDir]
    ]:
    """
    R/A/L のテキストリストから重複を除去し、最終的な R/A/L を返す。

    適用条件:
        - 図割あり（`is_multi_layouts=True`）かつ テキスト数が `len(R) + len(A) == len(L)` の場合のみ重複除去を適用。

    重複判定:
        - `R_texts_added + A_texts_added` を x 昇順に並べ、隣接要素の `(text, attr, dir)` が同一。
        - 同じインデックス位置の L 側でも `(text, attr, dir)` が同一であることを確認。
        - 条件一致時、隣接ペアの後者インデックス（`i+1`）を重複とみなして除去。

    Args:
        R_texts_added (List[ElementWithDir]): R の要素群。
        A_texts_added (List[ElementWithDir]): A の要素群。
        L_texts_added (List[ElementWithDir]): L の要素群。
        is_multi_layouts (bool): 図割ありかどうか。
        is_R_plus_A_equal_L (bool): `len(R) + len(A) == len(L)` の関係が成立しているか。

    Returns:
        Tuple[List[ElementWithDir], List[ElementWithDir], List[ElementWithDir]]:
            `(R_final, A_final, L_final)` の 3 要素タプル。

    Notes:
        - 適用条件を満たさない場合は入力そのままを返す。
        - 除去は R/A 結合側と、L 側に対して同じインデックス集合を用いて行います。
    """

    if is_multi_layouts and is_R_plus_A_equal_L:
        R_A = R_texts_added + A_texts_added
        R_A_sorted = sorted(R_A, key=lambda x: x[1][0])

        # 隣接要素の (text, attr, dir) が同一なら重複として index(i+1) を収集
        duplicate_idx: set[int] = set()
        for i in range(len(R_A_sorted) - 1):
            cur = R_A_sorted[i]
            nxt = R_A_sorted[i + 1]
            R_A_cur_key = (cur[0], cur[2], cur[3])
            R_A_nxt_key = (nxt[0], nxt[2], nxt[3])

            if R_A_cur_key == R_A_nxt_key:
                cur = L_texts_added[i]
                nxt = L_texts_added[i + 1]
                L_cur_key = (cur[0], cur[2], cur[3])
                L_nxt_key = (nxt[0], nxt[2], nxt[3])

                if L_cur_key == L_nxt_key:
                    duplicate_idx.add(i + 1)

        # 重複除去
        R_A_filtered = [item for i, item in enumerate(R_A_sorted) if i not in duplicate_idx]

        # 属性で分割
        R_final = split_by_attribute(R_A_filtered, "R")
        A_final = split_by_attribute(R_A_filtered, "A")

        # L 側も x でソートした後に同じ duplicate_idx を用いて除去
        L_sorted = sorted(L_texts_added, key=lambda x: x[1][0])
        L_final = [item for i, item in enumerate(L_sorted) if i not in duplicate_idx]
    else:
        R_final, A_final, L_final = R_texts_added, A_texts_added, L_texts_added

    return R_final, A_final, L_final


# ----------------------------
# Minimum extractions
# ----------------------------
def get_minimum_radius(R_texts: List[ElementWithDir]) -> Any:
    """
    1. 最小曲線半径を返す（R_texts の値を `float` 化した最小値）。

    Args:
        R_texts (List[ElementWithDir]): R の要素群（`(value, (x, y), 'R', dir)`）。

    Returns:
        Any:
            - 成功時: 最小の半径（`float`）。
            - 失敗時/要素なし: `"-"`。
    """

    if not R_texts:
        return "-"
    try:
        return min(float(text) for text, _, _, _ in R_texts)
    except Exception:
        return "-"


def get_minimum_easement_curve(
    R_texts: List[ElementWithDir],
    A_texts: List[ElementWithDir],
    L_texts: List[ElementWithDir]
) -> Any:
    """
    2. 最小緩和曲線長を返す。
        - `R + A` と `L` を x でソート。
        - インデックス対応かつ属性=A の位置の L を抽出し、その最小値を返す。
        - 配列長が一致しないなど条件不成立時は `"-"`。

    Args:
        R_texts (List[ElementWithDir]): R の要素群。
        A_texts (List[ElementWithDir]): A の要素群。
        L_texts (List[ElementWithDir]): L の要素群。

    Returns:
        Any:
            - 成功時: 最小 L（`float`）。
            - 条件不成立/抽出失敗: `"-"`。
    """

    R_A_sorted = sorted(R_texts + A_texts, key=lambda x: x[1][0])
    L_sorted = sorted(L_texts, key=lambda x: x[1][0])

    if len(R_A_sorted) != len(L_sorted):
        return "-"

    L_with_A: List[float] = []
    for i, (val_RA, _, attr_RA, _) in enumerate(R_A_sorted):
        if attr_RA == "A":
            try:
                L_with_A.append(float(L_sorted[i][0]))
            except Exception:
                # 変換失敗はスキップ
                pass

    return min(L_with_A) if L_with_A else "-"


def get_radius_that_can_omit_easement_curve(
        added_texts_sorted: List[ElementWithDir]
    ) -> Any:
    """
    3. 緩和曲線を省略できる曲線半径を返す。
        - ソート済み `added_texts_sorted` から、各 R と同じ x の「非 R 群」を参照。
        - 前後の x（非 R の隣接 x）に A が存在しない場合、その R を候補にする。
        - 候補 R の最小値を返す。該当なしなら `"-"`。

    Args:
        added_texts_sorted (List[ElementWithDir]): x 昇順の `(value, (x, y), attr, dir)`。

    Returns:
        Any:
            - 成功時: 最小の R（`float`）。
            - 該当なし: `"-"`。

    Notes:
        - 非 R を x ごとにグループ化し、順序付きの x リストで前後判定を行います。
    """

    added_is_R = split_by_attribute(added_texts_sorted, "R")
    added_not_R = split_by_attribute(added_texts_sorted, "R", True)

    # 非Rを x ごとにグループ化し、順序付きの x リストも作る
    from collections import defaultdict
    not_R_by_x = defaultdict(list)
    for el in added_not_R:
        x = el[1][0]
        not_R_by_x[x].append(el)
    x_list_not_R = sorted(not_R_by_x.keys())

    selected_R_values: List[float] = []

    for val_R, (x_R, _), attr_R, _ in added_is_R:
        # R と同じ x が非R側にもあるか確認
        if x_R not in not_R_by_x:
            # 前後判定ができないためスキップ（仕様踏襲）
            continue

        # 非R側 x の順序に基づき、前後の x を参照
        try:
            idx = x_list_not_R.index(x_R)
        except ValueError:
            # 念のための保険
            continue

        prev_x = x_list_not_R[idx - 1] if idx - 1 >= 0 else None
        next_x = x_list_not_R[idx + 1] if idx + 1 < len(x_list_not_R) else None

        prev_A_exists = any(el[2] == "A" for el in not_R_by_x.get(prev_x, [])) if prev_x is not None else False
        next_A_exists = any(el[2] == "A" for el in not_R_by_x.get(next_x, [])) if next_x is not None else False

        if not prev_A_exists and not next_A_exists:
            try:
                selected_R_values.append(float(val_R))
            except Exception:
                pass

    return min(selected_R_values) if selected_R_values else "-"


def get_minimum_curve(
    combined_texts_sorted: List[Element],
    min_y: float,
    max_y: float,
    center_y: float
) -> Tuple[Any, Any]:
    """
    4. 最小曲線長（設計速度 80km/h 未満 / 以上）を返す。

    走査仕様（既存ロジック維持）:
        - `A-R-R`（同方向）パターン: 次半径が規定倍率以下なら `A+R+R`、それ以外は `A+R` と次の `R` を候補。
            - <80km/h: 倍率 2
            - >=80km/h: 倍率 1.5
        - `A-R-A`（…R-A が連続の可能性）:
            - `A-R-A-R-A` の場合は合算（次1/次2 は not_L の値）
            - それ以外は `A+R+A`
        - その他: `R` 直下の `L` を候補に追加

    Args:
        combined_texts_sorted (List[Element]): x 昇順の `(value, (x, y), attr)`。
        min_y (float)   : 帯の下端 Y。
        max_y (float)   : 帯の上端 Y。
        center_y (float): 帯の中央 Y。

    Returns:
        Tuple[Any, Any]:
            `(min_less_80km_h, min_more_80km_h)`。
            - 値が存在しない場合は `"-"`。

    Notes:
        - 内部で `unify_close_x_coordinates` により x を統一し、
            `add_element_direction` により方向属性を付与してから走査します。
        - L 側とのインデックス対応を前提とした判定（既存仕様）を踏襲します。
    """

    curves_less_80km_h: List[float] = []
    curves_more_80km_h: List[float] = []

    unified = unify_close_x_coordinates(combined_texts_sorted, X_MERGE_THRESHOLD)
    added = add_element_direction(unified, min_y, max_y, center_y)

    added_is_L: List[ElementWithDir] = split_by_attribute(added, "L")
    added_not_L: List[ElementWithDir] = split_by_attribute(added, "L", True)

    i = 0
    while i < len(added_not_L):
        this_attr = added_not_L[i][2]
        this_dir = added_not_L[i][3]

        if this_attr == "R" and this_dir != "straight":
            prev_attr = added_not_L[i - 1][2] if i > 0 else ""
            next_attr = added_not_L[i + 1][2] if i < len(added_not_L) - 1 else ""
            next_dir  = added_not_L[i + 1][3] if i < len(added_not_L) - 1 else ""

            # A-R-R（同方向）パターン
            if prev_attr == "A" and next_attr == "R" and this_dir == next_dir:
                try:
                    this_radius = Decimal(str(added_not_L[i][0]))
                    next_radius = Decimal(str(added_not_L[i + 1][0]))

                    # L 側はインデックス対応を前提（原仕様維持）
                    if i - 1 >= 0 and i + 1 < len(added_is_L):
                        this_length = Decimal(str(added_is_L[i][0]))
                        prev_length = Decimal(str(added_is_L[i - 1][0]))
                        next_length = Decimal(str(added_is_L[i + 1][0]))
                    else:
                        # インデックス不整合時はスキップ
                        i += 1
                        continue

                    # < 80km/h
                    rate_less = Decimal("2")
                    if next_radius <= this_radius * rate_less:
                        length_A_R_R = this_length + prev_length + next_length
                        curves_less_80km_h.append(float(length_A_R_R))
                    else:
                        length_A_R = this_length + prev_length
                        curves_less_80km_h.append(float(length_A_R))
                        curves_less_80km_h.append(float(next_length))

                    # >= 80km/h
                    rate_more = Decimal("1.5")
                    if next_radius <= this_radius * rate_more:
                        length_A_R_R = this_length + prev_length + next_length
                        curves_more_80km_h.append(float(length_A_R_R))
                    else:
                        length_A_R = this_length + prev_length
                        curves_more_80km_h.append(float(length_A_R))
                        curves_more_80km_h.append(float(next_length))

                    i += 2
                    continue
                except Exception:
                    i += 1
                    continue

            # A-R-A（…R-A 連続の可能性チェック）
            if prev_attr == "A" and next_attr == "A":
                if i < len(added_not_L) - 3:
                    next1_attr = added_not_L[i + 2][2]
                    next1_dir = added_not_L[i + 2][3]
                    next2_attr = added_not_L[i + 3][2]

                    next1_is_R = (next1_attr == "R")
                    same_dir = (this_dir == next1_dir)
                    next2_is_A = (next2_attr == "A")
                    is_egg_shaped = next1_is_R and same_dir and next2_is_A

                    try:
                        # L インデックスに依存（原仕様維持）
                        if i - 1 >= 0 and i + 1 < len(added_is_L):
                            this_length = Decimal(str(added_is_L[i][0]))
                            prev_length = Decimal(str(added_is_L[i - 1][0]))
                            next_length = Decimal(str(added_is_L[i + 1][0]))
                        else:
                            i += 1
                            continue

                        if is_egg_shaped:
                            # A-R-A-R-A として合算（次1/次2 は not_L の値）
                            next1_length = Decimal(str(added_not_L[i + 2][0]))
                            next2_length = Decimal(str(added_not_L[i + 3][0]))
                            length = this_length + prev_length + next_length + next1_length + next2_length
                            v = float(length)
                            curves_less_80km_h.append(v)
                            curves_more_80km_h.append(v)
                            i += 4
                            continue
                        else:
                            length = this_length + prev_length + next_length
                            v = float(length)
                            curves_less_80km_h.append(v)
                            curves_more_80km_h.append(v)
                            i += 2
                            continue
                    except Exception:
                        i += 1
                        continue

            # その他：R 直下 L を取得
            try:
                if i < len(added_is_L):
                    this_length = Decimal(str(added_is_L[i][0]))
                    v = float(this_length)
                    curves_less_80km_h.append(v)
                    curves_more_80km_h.append(v)
            except Exception:
                pass

        # 次へ
        i += 1

    min_less = "-" if len(curves_less_80km_h) == 0 else min(curves_less_80km_h)
    min_more = "-" if len(curves_more_80km_h) == 0 else min(curves_more_80km_h)
    return min_less, min_more


# ----------------------------
# Main
# ----------------------------
def main(msp: Any, layer: str, paper_layout_count: int):
    """
    「曲率」帯のテキストから、以下 5 種の最小値を抽出して返す。

    返却タプル:
        1) `min_R_value` : 最小曲線半径
        2) `min_L_value_with_A` : 最小緩和曲線長（A と対応する L）
        3) `min_R_not_sandwiched_A` : 緩和曲線を省略できる曲線半径
        4) `min_L_value_with_R_less_80km_h` : 最小曲線長（設計速度 80km/h 未満）
        5) `min_L_value_with_R_more_80km_h` : 最小曲線長（設計速度 80km/h 以上）

    処理手順:
        1) 帯タイトル候補群を用いて上下端 (min_y, max_y) を探索。
        2) 範囲内 TEXT を抽出（`get_texts_in_range`）。
        3) 接頭辞ごとに R/A/L を抽出（`get_texts_replaced_prefix`）。
        4) `R + A == L` の関係が成立するか判定（成立時のみ詳細処理）。
        5) x を統一 → 方向付与 → 重複除去 → 属性分割。
        6) 1)〜4) の最小値を算出。

    Args:
        msp (Any): ezdxf の Modelspace。
        layer (str): 曲率帯のテキストが存在するレイヤー名。
        paper_layout_count (int): ペーパースペースのレイアウト数（図割有無の判定に使用）。

    Returns:
        Tuple[Any, Any, Any, Any, Any]:
            `(min_R_value, min_L_value_with_A, min_R_not_sandwiched_A,
                min_L_value_with_R_less_80km_h, min_L_value_with_R_more_80km_h)`。

    Notes:
        - 帯が見つからない場合は 5 要素すべて `"-"`。
        - `R + A == L` が成り立たない場合は、2)〜4) は `"-"` を返します（仕様踏襲）。
    """

    # 探索候補
    candidates = CURVATURE_TITLE_CANDIDATES

    # 帯の上端・下端 を探索
    min_y = max_y = None
    for label, c1, c2 in candidates:
        min_y, max_y = get_belt_y_positions(msp, layer, label, c1, c2)
        if min_y is not None and max_y is not None:
            break

    # 帯が見つからない場合は安全に早期終了
    if min_y is None or max_y is None:
        return "-", "-", "-", "-", "-"

    center_y = (min_y + max_y) / 2.0

    # 範囲内テキスト抽出
    texts_in_range = get_texts_in_range(msp, layer, min_y, max_y)

    # 接頭辞
    R_prefixes = CURVATURE_R_PREFIXES
    A_prefixes = CURVATURE_A_PREFIXES
    L_prefixes = CURVATURE_L_PREFIXES

    # 接頭辞ごとに抽出
    R_texts = get_texts_replaced_prefix(texts_in_range, R_prefixes, "R")
    A_texts = get_texts_replaced_prefix(texts_in_range, A_prefixes, "A")
    L_texts = get_texts_replaced_prefix(texts_in_range, L_prefixes, "L")

    # R=●● + A=●● == L=●● が成り立てば、必要なテキストエンティティが揃っているとみなす
    is_R_plus_A_equal_L = (len(R_texts) + len(A_texts) == len(L_texts))

    # R, A, L の配列を結合
    texts_combined = combine_and_sort_texts(R_texts, A_texts, L_texts)

    # 許容誤差内の x座標を揃える
    texts_unified = unify_close_x_coordinates(texts_combined, X_MERGE_THRESHOLD)

    # カーブ方向を付与する
    texts_added = add_element_direction(texts_unified, min_y, max_y, center_y)

    # 属性別に再度分ける
    R_texts_added = split_by_attribute(texts_added, "R")
    A_texts_added = split_by_attribute(texts_added, "A")
    L_texts_added = split_by_attribute(texts_added, "L")

    # 複数レイアウトか否か
    is_multi_layouts = (paper_layout_count >= 2)

    # 重複除去
    R_final, A_final, L_final = delete_the_same_curves(
        R_texts_added, A_texts_added, L_texts_added, is_multi_layouts, is_R_plus_A_equal_L
    )

    # 結合（x 昇順）
    texts_final = sorted(R_final + A_final + L_final, key=lambda x: x[1][0])

    # 1) 最小曲線半径
    min_R_value = get_minimum_radius(R_final)

    # 2) 最小緩和曲線長
    # 3) 緩和曲線を省略出来る曲線半径
    # 4) 最小曲線長（設計速度 80km/h 未満・以上）
    if is_R_plus_A_equal_L:
        min_L_value_with_A = get_minimum_easement_curve(R_final, A_final, L_final)
        min_R_not_sandwiched_A = get_radius_that_can_omit_easement_curve(texts_final)
        (
            min_L_less,
            min_L_more
        ) = get_minimum_curve(texts_final, min_y, max_y, center_y)
    else:
        min_L_value_with_A = "-"
        min_R_not_sandwiched_A = "-"
        min_L_less = "-"
        min_L_more = "-"

    return (
        min_R_value,
        min_L_value_with_A,
        min_R_not_sandwiched_A,
        min_L_less,
        min_L_more,
    )

# ----------------------------
# Entry Point
# ----------------------------
if __name__ == "__main__":
    pass
