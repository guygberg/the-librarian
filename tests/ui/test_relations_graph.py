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


def test_edge_kind_filter_hides_other_kinds(page, ui):
    ui, item = graph_page(page, ui)
    kinds = {e["kind"] for e in api_graph(page, item, 1)["edges"]}
    assert len(kinds) > 1
    keep = sorted(kinds)[0]
    for kind in sorted(kinds - {keep}):
        kind_chip(page, kind).click()
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
    expect(page.locator("[data-part=graph-edge][data-kind='evidence']").first).to_be_visible()
    expect(page.locator("[data-part=graph-node].source_item").first).to_contain_text('"')
    kind_chip(page, "evidence").click()
    expect(page.locator("[data-part=kind][data-kind='evidence']")).to_have_class("chip")
    url = page.url
    page.reload()
    assert page.url == url
    expect(page.locator("[data-part=kind][data-kind='evidence']")).to_have_class("chip")
    expect(page.locator("[data-part=graph-edge][data-kind='evidence']")).to_have_count(0)
