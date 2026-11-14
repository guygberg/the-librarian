from urllib.parse import unquote

from playwright.sync_api import expect

from fixtures.scenarios import payments_cutover as payments
from support.ui_stream import STAMP, person, record

FETCH = """async (path) => {
  const token = document.querySelector('meta[name="librarian-token"]').content;
  return (await fetch(path, { headers: { 'X-Librarian-Token': token } })).json();
}"""


def centre_id(ui):
    return ui.sql("SELECT id FROM records WHERE title = ?", payments.NOV_18)[0][0]


def link(ui, kind, a, b):
    ui.sql(
        "INSERT INTO links (workspace, type, from_type, from_id, to_type, to_id, created_at)"
        " VALUES ('work', ?, ?, ?, ?, ?, ?)",
        kind,
        *a,
        *b,
        STAMP,
    )


def graph_page(page, ui, query=""):
    """The cutover Record, plus a Person it waits on, a related Record and one more Record two
    hops out."""
    ui = ui("payments-cutover", payments.NOW)
    item = centre_id(ui)
    raz = person(ui, "Raz")
    sandbox = record(ui, "Get Acme sandbox keys")
    webhook = record(ui, "Webhook v2 migration")
    link(ui, "waiting_on", ("record", item), ("person", raz))
    link(ui, "related_to", ("record", item), ("record", sandbox))
    link(ui, "blocks", ("record", sandbox), ("record", webhook))
    link(ui, "supersedes", ("record", webhook), ("record", sandbox))
    page.goto(f"{ui.url}/items/{item}?kind=decisions&tab=relations{query}")
    expect(page.locator("[data-part=relations-graph]")).to_be_visible()
    return ui, item


def nodes(page, hop=None):
    return page.locator("[data-part=graph-node]" + (f".hop-{hop}" if hop else ""))


def kind_chip(page, kind):
    details = page.locator("[data-part=kind-filter]")
    if details.get_attribute("open") is None:
        details.locator("summary").click()
    return page.locator(f"[data-part=kind][data-kind='{kind}']")


def api_graph(page, item, hops, kinds=""):
    return page.evaluate(FETCH, f"/api/graph?center=record:{item}&hops={hops}&kinds={kinds}")


def test_opens_at_one_hop_centred_on_the_item(page, ui):
    ui, item = graph_page(page, ui)
    expected = api_graph(page, item, 1)
    assert len(expected["nodes"]) > 1
    expect(nodes(page)).to_have_count(len(expected["nodes"]))
    expect(page.locator("[data-part=graph-node].center")).to_have_attribute(
        "data-id", f"record:{item}"
    )
    expect(page.locator("[data-part=graph-node].center")).to_contain_text(payments.NOV_18[:20])
    expect(nodes(page, 2)).to_have_count(0)
    expect(page.locator("[data-part=hop] >> nth=0")).to_have_class("chip on")


def test_hop_control_adds_nodes_and_fades_outer_hops(page, ui):
    ui, item = graph_page(page, ui)
    for hops in (2, 3):
        page.locator(f"[data-part=hop][data-hops='{hops}']").click()
        expected = api_graph(page, item, hops)
        expect(nodes(page)).to_have_count(len(expected["nodes"]))
        assert f"hops={hops}" in page.url
        for hop in range(1, hops + 1):
            expect(nodes(page, hop)).to_have_count(sum(n["hop"] == hop for n in expected["nodes"]))
    assert len(api_graph(page, item, 2)["nodes"]) > len(api_graph(page, item, 1)["nodes"])
    faded = nodes(page, 2).first
    assert float(faded.evaluate("el => getComputedStyle(el).opacity")) < 1
    assert float(nodes(page, 1).first.evaluate("el => getComputedStyle(el).opacity")) == 1


def test_edge_labels_do_not_overlap_at_two_hops(page, ui):
    graph_page(page, ui, "&hops=2")
    # Everything in the SVG's own units, so the checks do not depend on the page zoom.
    scene = page.evaluate(
        """() => {
          const svg = document.querySelector('[data-part=relations-graph]');
          const o = svg.getBoundingClientRect();
          const k = o.width / svg.viewBox.baseVal.width;
          const box = (r) => ({ l: (r.left - o.left) / k, r: (r.right - o.left) / k,
                                t: (r.top - o.top) / k, b: (r.bottom - o.top) / k });
          const edges = [...svg.querySelectorAll('[data-part=graph-edge]')].map((g, i) => {
            const ln = g.querySelector('line');
            const [x1, y1, x2, y2] = ['x1', 'y1', 'x2', 'y2'].map((a) => +ln.getAttribute(a));
            const tx = g.querySelector('text');
            const title = g.querySelector('title').textContent;
            return { i, x1, y1, x2, y2, kind: g.dataset.kind, title,
                     text: tx && tx.textContent, box: tx && box(tx.getBoundingClientRect()) };
          });
          const rects = svg.querySelectorAll('[data-part=graph-node] rect');
          const nodes = [...rects].map((r) => box(r.getBoundingClientRect()));
          return { edges, nodes };
        }"""
    )
    edges, nodes_ = scene["edges"], scene["nodes"]

    def apart(a, b):
        return a["r"] <= b["l"] or b["r"] <= a["l"] or a["b"] <= b["t"] or b["b"] <= a["t"]

    labelled = [e for e in edges if e["box"]]
    assert len(labelled) > 3
    for a in labelled:
        assert a["text"] == a["title"], a
        for n in nodes_:
            assert apart(a["box"], n), f"label behind a node: {a} {n}"
        for other in edges:
            if other["i"] == a["i"]:
                continue
            if other["i"] > a["i"] and other["box"]:
                assert apart(a["box"], other["box"]), f"labels overlap: {a} {other}"
            for k in range(101):
                x = other["x1"] + (other["x2"] - other["x1"]) * k / 100
                y = other["y1"] + (other["y2"] - other["y1"]) * k / 100
                b = a["box"]
                inside = b["l"] < x < b["r"] and b["t"] < y < b["b"]
                assert not inside, f"label {a} over line {other}"

    # Parallel edges (same pair of nodes, either direction) fan apart and keep one label each.
    def mid(e):
        return (e["x1"] + e["x2"]) / 2, (e["y1"] + e["y2"]) / 2

    pairs = [
        (a, b)
        for i, a in enumerate(edges)
        for b in edges[i + 1 :]
        if abs(mid(a)[0] - mid(b)[0]) < 30 and abs(mid(a)[1] - mid(b)[1]) < 30
    ]
    kinds = {frozenset((a["kind"], b["kind"])) for a, b in pairs}
    wanted = {frozenset(("belongs_to", "blocks")), frozenset(("blocks", "supersedes"))}
    assert wanted <= kinds, kinds
    for a, b in pairs:
        if "supersedes" in {a["kind"], b["kind"]}:
            assert a["box"] and b["box"], f"reciprocal edge lost its label: {a} {b}"
        gap = ((mid(a)[0] - mid(b)[0]) ** 2 + (mid(a)[1] - mid(b)[1]) ** 2) ** 0.5
        assert gap > 5, f"parallel edges drawn on one line: {a} {b}"


def test_a_label_with_no_free_spot_is_left_off(page, ui):
    graph_page(page, ui)
    placed = page.evaluate(
        """async () => {
          const { clearSpot } = await import('/static/views/graph.js');
          const [a, b] = [[0, 0], [200, 0]];
          const free = clearSpot(a, b, [100, 0], 'blocks', [], []);
          const taken = [];
          for (let x = -100; x <= 300; x += 10) for (let y = -60; y <= 60; y += 6)
            taken.push({ l: x - 40, r: x + 40, t: y - 15, b: y + 3 });
          return { free, crowded: clearSpot(a, b, [100, 0], 'blocks', taken, []) };
        }"""
    )
    assert placed["free"] is not None
    assert placed["crowded"] is None


def test_parallel_edges_fan_to_opposite_sides_whichever_way_they_point(page, ui):
    graph_page(page, ui)
    offsets = page.evaluate(
        """async () => {
          const { fanOut } = await import('/static/views/graph.js');
          const [a, b] = [[0, 0], [100, 0]];
          return { first: fanOut(a, b, 0, 2), second: fanOut(a, b, 1, 2),
                   alone: fanOut(a, b, 0, 1) };
        }"""
    )
    assert offsets["first"][1] == -offsets["second"][1] != 0
    assert offsets["alone"] == [0, 0]


def test_edge_kind_filter_hides_other_kinds(page, ui):
    ui, item = graph_page(page, ui)
    kinds = {e["kind"] for e in api_graph(page, item, 1)["edges"]}
    assert len(kinds) > 1
    keep = sorted(kinds)[0]
    for kind in sorted(kinds - {keep}):
        kind_chip(page, kind).click()
        # The next chip's link is built from the state drawn, so wait for this click to settle.
        expect(kind_chip(page, kind)).not_to_have_class("chip on")
    shown = {e["kind"] for e in api_graph(page, item, 1, keep)["edges"]}
    assert shown == {keep}
    expect(page.locator("[data-part=graph-edge]")).to_have_count(
        len(api_graph(page, item, 1, keep)["edges"])
    )
    assert page.locator(f"[data-part=graph-edge]:not([data-kind='{keep}'])").count() == 0
    assert f"kinds={keep}" in page.url
    # Turning every other kind back on drops the parameter.
    for kind in sorted(kinds - {keep}):
        kind_chip(page, kind).click()
        expect(kind_chip(page, kind)).to_have_class("chip on")
    assert "kinds=" not in page.url or all(k in page.url for k in kinds)


def test_clicking_a_node_recentres_and_reload_restores_the_view(page, ui):
    ui, item = graph_page(page, ui, "&hops=2")
    other = next(n for n in api_graph(page, item, 1)["nodes"] if n["hop"] == 1)
    page.locator(f"[data-part=graph-node][data-id='{other['id']}']").click()
    expect(page.locator("[data-part=graph-node].center")).to_have_attribute("data-id", other["id"])
    assert unquote(page.url).count(f"center={other['id']}") == 1
    assert "hops=2" in page.url

    url = page.url
    page.reload()
    expect(page.locator("[data-part=graph-node].center")).to_have_attribute("data-id", other["id"])
    assert page.url == url
    expect(page.locator("[data-part=hop][data-hops='2']")).to_have_class("chip on")
    expected = page.evaluate(FETCH, f"/api/graph?center={other['id']}&hops=2&kinds=")
    expect(nodes(page)).to_have_count(len(expected["nodes"]))


def test_reload_restores_edge_kind_filter(page, ui):
    ui, item = graph_page(page, ui)
    # An edge drawn through a node may have no free label spot, so look at a label, not a bare line.
    label = page.locator("[data-part=graph-edge][data-kind='evidence'] text").first
    expect(label).to_be_visible()
    expect(page.locator("[data-part=graph-node].source_item").first).to_contain_text('"')
    kind_chip(page, "evidence").click()
    expect(page.locator("[data-part=kind][data-kind='evidence']")).to_have_class("chip")
    url = page.url
    page.reload()
    assert page.url == url
    expect(page.locator("[data-part=kind][data-kind='evidence']")).to_have_class("chip")
    expect(page.locator("[data-part=graph-edge][data-kind='evidence']")).to_have_count(0)
