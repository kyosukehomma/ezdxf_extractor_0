from typing import Any, Dict, List, Optional, Tuple, Iterable

def filter_anchors_without_text_between(
    anchor_points: List[Tuple[float, float]],
    line_y: Optional[float],
    direction: str,
    all_texts: List[Tuple[float, float]],
    eps: float = 1e-6
) -> List[Tuple[float, float]]:
    """
    アンカー点のうち、指定方向（down/up）において「アンカーと境界線の間」に TEXT が存在しないものだけを残す。
        - `line_y` が `None` の場合（境界線が見つからない場合）はフィルタを行わず、そのまま `anchor_points` を返す。
        - `direction="down"` の場合、x がほぼ同じ（`abs(tx - x) <= eps`）で、`line_y < ty < y` を満たす TEXT が介在していないアンカーだけを残す。
        - `direction="up"` の場合、x がほぼ同じで、`y < ty < line_y` を満たす TEXT が介在していないアンカーだけを残す。
        - x 座標の一致判定は許容誤差 `eps` により近接同一とみなす。

    Args:
        anchor_points (List[Tuple[float, float]]): アンカー候補の座標リスト（各要素は `(x, y)`）。
        line_y (Optional[float]): 比較対象となる境界線の Y 座標。`None` の場合はフィルタをスキップ。
        direction (str): フィルタ方向。`"down"`（アンカーの直下を確認）または `"up"`（アンカーの直上を確認）。
        all_texts (List[Tuple[float, float]]): 図面内の TEXT の座標一覧（各要素は `(tx, ty)`）。
        eps (float): x 座標の一致判定に用いる許容誤差。デフォルト `1e-6`。

    Returns:
        List[Tuple[float, float]]: 条件を満たすアンカー点のみを残した座標リスト。

    Notes:
        - x の一致は `abs(tx - x) <= eps` で判定します。わずかなずれを許容するための近接同一判定です。
        - `direction` の値は `"down"` / `"up"` のみを想定しています（その他の値の場合は `"up"` と同様の分岐へ進みます）。
        - 「間に TEXT が存在する」場合はアンカーを除外し、存在しない場合のみ採用します。
    """

    if line_y is None:
        return anchor_points  # LINEが見つからなかった場合はフィルタしない

    filtered = []
    for x, y in anchor_points:
        if direction == "down":
            between_texts = [
                (tx, ty) for tx, ty in all_texts
                if abs(tx - x) < eps and line_y < ty < y
            ]
        else:  # "up"
            between_texts = [
                (tx, ty) for tx, ty in all_texts
                if abs(tx - x) < eps and y < ty < line_y
            ]
        if not between_texts:
            filtered.append((x, y))

    return filtered

def main(
    msp,
    *,
    text_layer: str,
    anchor_down: str,
    anchor_up: str,
    pick_down: str = "min",
    pick_up: str = "max",
    eps: float = 1e-6,
    line_layers: Optional[List[str]] = None,
    min_horizontal_length: float = 0.0,
    exact_match: bool = True,
    round_digits: int = 6,
) -> Dict[str, Any]:
    """
    アンカーとなる2つのテキストの周囲にある最も近い水平方向の境界線 (帯の上端・下端) を見つける
        - polyline_to_line_keep_others.py で LWPOLYLINE を LINE に変換して取り扱う

    Args:
        msp: モデルスペース
        text_layer:                 アンカーとなる文字 (TEXT/MTEXT) があるレイヤ
        anchor_down:                下方向の近傍線を探すときの基準文字 (例: '曲' や '勾')
        anchor_up:                  上方向の近傍線を探すときの基準文字 (例: '率' や '配')
        pick_down:                  anchor_downが複数ヒットした場合の y座標 の選び方 ('min' or 'max')
        pick_up:                    anchor_upが複数ヒットした場合の y座標 の選び方 ('min' or 'max')
        eps:                        水平判定や閾値比較の許容誤差イプシロン (1e-6)
        line_layers(Optional):      帯の線があるレイヤ名リスト (None なら全レイヤ対象)
        min_horizontal_length:      この長さ未満の水平線分は除外 (小さな記号除外用)
        exact_match:                True ならテキスト一致を「等価(==)」で判定, Falseなら部分一致
        round_digits:               丸め桁数

    Returns:
        Dict[str, Any]:
            - exists_by_keyword:    {anchor_down: bool, anchor_up: bool}
            - has_both_anchors:     両アンカーが見つかったか
            - positions:            {anchor_text: [(x, y), ...]}
            - anchor_down_point:    (x, y) 選ばれた anchor_down の座標
            - anchor_up_point:      (x, y) 選ばれた anchor_up の座標
            - bottom_y:             anchor_down の y より下で最も近い水平線の y
            - top_y:                anchor_up の y より上で最も近い水平線の y
            - segments_examined:    評価した水平セグメント数
    """

    # --- 1) アンカーテキストの座標収集 (TEXT) ---
    def _match(s: str, token: str) -> bool:
        """
        テキスト s が token と一致するか、または部分一致するかを判定する内部関数。
            - `exact_match=True` の場合: 文字列の完全一致（`s == token`）で判定。
            - `exact_match=False` の場合: 部分一致（`token in s`）で判定。

        Args:
            s (str): 対象文字列。
            token (str): 検索したい語句。

        Returns:
            bool: 一致（完全一致または部分一致）と判定されれば True。

        Notes:
            - `exact_match` は外側スコープの変数に依存しており、本関数の引数ではない点に注意。
            - `token` が複数文字でも部分一致により内部に含まれていれば True。
            - 大文字小文字の区別はそのまま行われる（lower/upper 変換は行わない）。
        """
        # return s == token if exact_match else token in s
        if exact_match:
            return s == token
        else:
            return token in s


    positions: Dict[str, List[Tuple[float, float]]] = {anchor_down: [], anchor_up: []}

    for ent in msp.query(f'TEXT[layer=="{text_layer}"]'):
        content = ent.dxf.text if ent.dxftype() == "TEXT" else ent.plain_text()
        content = content or ""

        ins = ent.dxf.insert    # (x, y, z)
        xy = (float(ins[0]), float(ins[1]))
        if _match(content, anchor_down):
            positions[anchor_down].append(xy)
        if _match(content, anchor_up):
            positions[anchor_up].append(xy)

    exists_down = bool(positions[anchor_down])
    exists_up =   bool(positions[anchor_up])

    # アンカーが足りなければ return
    if not (exists_down and exists_up):
        return {
            "exists_by_keyword": {anchor_down: exists_down, anchor_up: exists_up},
            "has_both_anchors": False,
            "positions": positions,
            "anchor_down_point": None,
            "anchor_up_point": None,
            "bottom_y": None,
            "top_y": None,
            "segments_examined": 0,
        }

    # --- 2) アンカー点を決定 (y の min/max を選ぶ) ---
    def _select(
        points: List[Tuple[float, float]],
        which: str
    ) -> Tuple[float, float]:
        """
        アンカーポイント群から、Y座標の最小値または最大値を持つ点を 1 つ選んで返す内部関数。
            - `which == "min"` の場合、Y 座標が最小の点を返す。
            - `which == "max"` の場合、Y 座標が最大の点を返す。
            - 上記以外の値が `which` に指定された場合は `ValueError` を送出する。

        Args:
            points (List[Tuple[float, float]]): `(x, y)` の座標タプルのリスト。Y 座標で比較される。
            which (str): 選択方法 `"min"` または `"max"`。

        Returns:
            Tuple[float, float]: 選択された `(x, y)` 座標。

        Raises:
            ValueError: `which` が `"min"`・`"max"` のいずれでもない場合。

        Notes:
            - `min(points, key=lambda p: p[1])` により Y 座標のみを比較して選択します。
            - 空リストが渡された場合は `min()` / `max()` により `ValueError` が発生する。
                - しかし、呼び出し側が常に 1 個以上のアンカーを前提にしているため、仕様として許容。
        """
        if which == "min":
            return min(points, key=lambda p: p[1])
        if which == "max":
            return max(points, key=lambda p: p[1])
        raise ValueError("which must be 'min' or 'max'")


    anchor_down_point = _select(positions[anchor_down], pick_down)
    anchor_up_point   = _select(positions[anchor_up],   pick_up)

    x_down, y_down = anchor_down_point
    x_up  , y_up   = anchor_up_point

    # --- 3) 水平セグメントの収集 (LINE, LWPOLYLINE, ブロック内も可) ---
    segments: List[Tuple[float, float, float]] = []  #(xL, y, xR)


    def layer_ok(ent) -> bool:
        """
        線分エンティティ `ent` が帯境界探索の対象レイヤーに属しているかを判定する内部関数。
            - `line_layers` が `None` または空（Falsy）の場合は、すべてのレイヤーを対象（True）。
            - `line_layers` が指定されている場合は、`ent.dxf.layer` がその中に含まれていれば True。

        Args:
            ent: ezdxf のエンティティ（主に `LINE` を想定）。`ent.dxf.layer` を参照する。

        Returns:
            bool: 対象レイヤーなら True、対象外なら False。

        Notes:
            - `line_layers` は外側スコープの変数に依存しています（本関数の引数ではありません）。
            - 複数レイヤーを指定して水平セグメント収集を限定したい場合に用います。
        """
        result_1 = (not line_layers)
        if line_layers is not None:
            result_2 = (ent.dxf.layer in line_layers)
        return result_1 or result_2


    def add_seg(x1: float, y1: float, x2: float, y2: float):
        """
        2 点 `(x1, y1)` と `(x2, y2)` から、水平線分（ほぼ同一 Y）であれば
        セグメント `(xL, yq, xR)` を収集リスト `segments` に追加する内部関数。
            - `abs(y1 - y2) <= eps` の場合のみ「水平」とみなす（許容誤差 `eps` は外側スコープの値）。
            - `min_horizontal_length` が指定されている場合、その長さ未満の水平線分は除外。
            - `xL, xR` は左端/右端としてソートして格納（`xL <= xR` を保証）。
            - `yq` は `(y1 + y2) / 2` を `round_digits` 桁で丸めた代表値として格納（微小差の統合目的）。

        Args:
            x1 (float): 点1の X 座標。
            y1 (float): 点1の Y 座標。
            x2 (float): 点2の X 座標。
            y2 (float): 点2の Y 座標。

        Returns:
            None: ※条件を満たす場合に限り、`segments.append((xL, yq, xR))` を実行します。

        Notes:
            - `eps`, `min_horizontal_length`, `round_digits`, `segments` は外側スコープの変数に依存します。
            - 「水平判定」は `abs(y1 - y2) <= eps` のみで行い、`yq` は平均値の丸めにより近接値を統合します。
            - 極端に短い水平線分（記号やノイズ）を除外するため `min_horizontal_length` を設けています。
            - 斜線や垂直線は追加されません（水平条件を満たさないため）。
        """
        y_diff = abs(y1 - y2)
        if y_diff <= eps:
            pass
            if min_horizontal_length and abs(x2 - x1) < min_horizontal_length:
                return
            xL, xR= (x1, x2) if x1 <= x2 else (x2, x1)
            yq = round(0.5 * (y1 + y2), round_digits)   # 微小差を丸めて統合
            segments.append((xL, yq, xR))
        else:
            pass


    # LINE
    lns = msp.query('LINE')

    for ln in lns:
        if not layer_ok(ln):
            continue
        p1, p2 = ln.dxf.start, ln.dxf.end
        add_seg(float(p1[0]), float(p1[1]), float(p2[0]), float(p2[1]))


    # --- 4) アンカー x 付近だけに絞りたい場合のフィルタ ---

    def contains_x(xL: float, xR: float, x0: float, eps: float = 1e-6) -> bool:
        """
        水平線セグメント (xL, xR) の範囲にアンカーの x 座標 x0 が含まれているかを判定する。

        Args:
            xL (float): セグメントの左端 x 座標
            xR (float): セグメントの右端 x 座標
            x0 (float): アンカーの x 座標
            eps (float): 許容誤差（デフォルトは 1e-6）

        Returns:
            bool: x0 が xL ～ xR の範囲に含まれていれば True

        Notes:
            LINEは、必ずしも左から右とは限らないので、最小値と最大値で振り分ける
        """
        left  = min(xL, xR)
        right = max(xL, xR)
        return (left - eps) <= x0 <= (right + eps)

    # 仮アンカー選定（フィルタ前）
    anchor_down_point = _select(positions[anchor_down], pick_down)
    anchor_up_point   = _select(positions[anchor_up]  , pick_up)
    x_down, y_down = anchor_down_point
    x_up  , y_up   = anchor_up_point

    # 帯タイトル下部の TEXT で, x座標が 水平LINE の 始点x と 終点x に挟まれているものの y座標 だけを集める
    cands_down = set()
    for xL, y, xR in segments:
        if contains_x(xL, xR, x_down):
            cands_down.add(y)

    # 帯タイトル上部の TEXT で, x座標が 水平LINE の 始点x と 終点x に挟まれているものの y座標 だけを集める
    cands_up = set()
    for xL, y, xR in segments:
        if contains_x(xL, xR, x_up):
            cands_up.add(y)


    # --- 5) 直下/直上の最近棒を決定 (同高は除外) ---
    def nearest_below(cands: Iterable[float], y: float) -> Optional[float]:
        """
        候補集合 `cands` の中から、基準値 `y` より 下側（小さい） にある値のうち最も近い（最大の）ものを返す。
            - 「同高」は除外するため、`c < y - eps` を満たす値のみを対象とする。
            - 対象が存在する場合はその最大値（= y に最も近い下側）を返す。
            - 対象が無い場合は `None` を返す。

        Args:
            cands (Iterable[float]): 比較対象となる数値の反復可能な集合。
            y (float): 基準となる値。

        Returns:
            Optional[float]:
                - 成功時: `y` より下側で最も近い値（最大値）。
                - 対象なし: `None`。

        Notes:
            - 許容誤差 `eps` は外側スコープの変数に依存します（本関数の引数ではありません）。
            - 「同高（ほぼ同一）」を除外し、確実に下側にある値だけを対象とします。
        """
        vals = []
        for c in cands:
            if c < y - eps:
                vals.append(c)

        return max(vals) if vals else None


    def nearest_above(cands: Iterable[float], y: float) -> Optional[float]:
        """
        候補集合 `cands` の中から、基準値 `y` より 上側（大きい） にある値のうち最も近い（最小の）ものを返す。
            - 「同高」は除外するため、`c > y + eps` を満たす値のみを対象とする。
            - 対象が存在する場合はその最小値（= y に最も近い上側）を返す。
            - 対象が無い場合は `None` を返す。

        Args:
            cands (Iterable[float]): 比較対象となる数値の反復可能な集合。
            y (float): 基準となる値。

        Returns:
            Optional[float]:
                - 成功時: `y` より上側で最も近い値（最小値）。
                - 対象なし: `None`。

        Notes:
            - 許容誤差 `eps` は外側スコープの変数に依存します（本関数の引数ではありません）。
            - 「同高（ほぼ同一）」を除外し、確実に上側にある値だけを対象とします。
        """
        vals = []
        for c in cands:
            if c > y + eps:
                vals.append(c)

        return min(vals) if vals else None


    bottom_y = nearest_below(cands_down, y_down)    # anchor_down の直下
    top_y    = nearest_above(cands_up,   y_up)      # anchor_up   の直上

    # 全TEXT座標取得（text_layer限定）
    all_text_positions: List[Tuple[float, float]] = [
        (float(ent.dxf.insert[0]), float(ent.dxf.insert[1]))
        for ent in msp.query(f'TEXT[layer=="{text_layer}"]')
    ]

    # アンカー候補をフィルタリング
    positions[anchor_down] = filter_anchors_without_text_between(
        positions[anchor_down], bottom_y, "down", all_text_positions, eps
    )

    positions[anchor_up] = filter_anchors_without_text_between(
        positions[anchor_up], top_y, "up", all_text_positions, eps
    )

    exists_down = bool(positions[anchor_down])
    exists_up   = bool(positions[anchor_up])

    if not (exists_down and exists_up):
        return {
            "exists_by_keyword": {anchor_down: exists_down, anchor_up: exists_up},
            "has_both_anchors": False,
            "positions": positions,
            "anchor_down_point": None,
            "anchor_up_point": None,
            "bottom_y": bottom_y,
            "top_y": top_y,
            "segments_examined": len(segments),
        }

    # フィルタ後のアンカーから選定
    anchor_down_point = _select(positions[anchor_down], pick_down)
    anchor_up_point   = _select(positions[anchor_up]  , pick_up)
    x_down, y_down = anchor_down_point
    x_up  , y_up   = anchor_up_point

    # 帯タイトル下部の TEXT で, x座標が 水平LINE の 始点x と 終点x に挟まれているものの y座標 だけを集める
    cands_down = set()
    for xL, y, xR in segments:
        if contains_x(xL, xR, x_down):
            cands_down.add(y)

    # 帯タイトル上部の TEXT で, x座標が 水平LINE の 始点x と 終点x に挟まれているものの y座標 だけを集める
    cands_up = set()
    for xL, y, xR in segments:
        if contains_x(xL, xR, x_up):
            cands_up.add(y)

    bottom_y = nearest_below(cands_down, y_down)    # anchor_down の直下
    top_y    = nearest_above(cands_up,   y_up)      # anchor_up   の直上

    return {
        "exists_by_keyword": {anchor_down: exists_down, anchor_up: exists_up},
        "has_both_anchors": True,
        "positions": positions,
        "anchor_down_point": anchor_down_point,
        "anchor_up_point": anchor_up_point,
        "bottom_y": bottom_y,
        "top_y": top_y,
        "segments_examined": len(segments),
    }

# ----------------------------
# Entry Point
# ----------------------------
if __name__ == "__main__":
    pass