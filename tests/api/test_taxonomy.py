"""Smoke tests for /api/taxonomy endpoints (genre graph, kept for the future
genre explorer — see Q1b-2). One test per endpoint: status + minimal shape,
including the camelCase keys that are part of the public JSON contract."""
from urllib.parse import quote

import pytest_asyncio
from models import GenreEdge, GenreMapping, GenreNode


@pytest_asyncio.fixture
async def graph(db):
    """Mini genre graph: electronic (root) <- house <- deep house,
    disco (root) -influence-> house, plus one mapped and one unmapped raw name."""
    electronic = GenreNode(wikidata_id="Q9778", label="electronic music")
    house = GenreNode(wikidata_id="Q20502", label="house")
    deep_house = GenreNode(wikidata_id="Q1265336", label="deep house")
    disco = GenreNode(wikidata_id="Q104817", label="disco")
    db.add_all([electronic, house, deep_house, disco])
    await db.flush()

    db.add_all([
        GenreEdge(from_node_id=house.id, to_node_id=electronic.id,
                  type="parent", source="wikidata"),
        GenreEdge(from_node_id=deep_house.id, to_node_id=house.id,
                  type="parent", source="wikidata"),
        GenreEdge(from_node_id=disco.id, to_node_id=house.id,
                  type="influence", source="wikidata"),
        GenreMapping(raw_name="Deep House", node_id=deep_house.id),
        GenreMapping(raw_name="Future Rave", node_id=None),
    ])
    await db.commit()

    return {
        "electronic": electronic,
        "house": house,
        "deep_house": deep_house,
        "disco": disco,
    }


class TestListNodes:
    async def test_no_query(self, client, graph):
        r = await client.get("/api/taxonomy/nodes")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 4
        assert [n["label"] for n in data["items"]] == [
            "deep house", "disco", "electronic music", "house",
        ]
        assert data["items"][0]["wikidataId"] == "Q1265336"

    async def test_with_query(self, client, graph):
        r = await client.get("/api/taxonomy/nodes", params={"q": "house"})
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        assert {n["label"] for n in data["items"]} == {"house", "deep house"}

    async def test_query_escapes_like_metacharacters(self, client, graph):
        # "%" must match literally, not as a wildcard (A1-18: like_escape)
        r = await client.get("/api/taxonomy/nodes", params={"q": "hou%e"})
        assert r.status_code == 200
        assert r.json()["total"] == 0


class TestGetNode:
    async def test_found(self, client, graph):
        r = await client.get(f"/api/taxonomy/nodes/{graph['house'].id}")
        assert r.status_code == 200
        data = r.json()
        assert data == {
            "id": graph["house"].id, "wikidataId": "Q20502", "label": "house",
        }

    async def test_404(self, client, graph):
        r = await client.get("/api/taxonomy/nodes/999999")
        assert r.status_code == 404


class TestChildren:
    async def test_parent_edges_only(self, client, graph):
        r = await client.get(f"/api/taxonomy/nodes/{graph['house'].id}/children")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["label"] == "deep house"
        assert items[0]["edgeType"] == "parent"
        assert items[0]["edgeSource"] == "wikidata"
        assert items[0]["wikidataId"] == "Q1265336"

    async def test_include_influence(self, client, graph):
        r = await client.get(
            f"/api/taxonomy/nodes/{graph['house'].id}/children",
            params={"include_influence": "true"},
        )
        assert r.status_code == 200
        items = r.json()["items"]
        assert {(i["label"], i["edgeType"]) for i in items} == {
            ("deep house", "parent"), ("disco", "influence"),
        }


class TestParents:
    async def test_shape(self, client, graph):
        r = await client.get(f"/api/taxonomy/nodes/{graph['house'].id}/parents")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["label"] == "electronic music"
        assert items[0]["edgeType"] == "parent"
        assert items[0]["wikidataId"] == "Q9778"


class TestAncestors:
    async def test_recursive_depth(self, client, graph):
        r = await client.get(f"/api/taxonomy/nodes/{graph['deep_house'].id}/ancestors")
        assert r.status_code == 200
        items = r.json()["items"]
        assert [(i["label"], i["depth"]) for i in items] == [
            ("house", 1), ("electronic music", 2),
        ]
        assert items[0]["wikidataId"] == "Q20502"


class TestDescendants:
    async def test_recursive_depth(self, client, graph):
        r = await client.get(
            f"/api/taxonomy/nodes/{graph['electronic'].id}/descendants"
        )
        assert r.status_code == 200
        items = r.json()["items"]
        assert [(i["label"], i["depth"]) for i in items] == [
            ("house", 1), ("deep house", 2),
        ]
        assert items[0]["wikidataId"] == "Q20502"


class TestNeighbors:
    async def test_influenced_by(self, client, graph):
        r = await client.get(f"/api/taxonomy/nodes/{graph['house'].id}/neighbors")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["label"] == "disco"
        assert items[0]["direction"] == "influenced_by"
        assert items[0]["edgeSource"] == "wikidata"
        assert items[0]["wikidataId"] == "Q104817"

    async def test_influences(self, client, graph):
        r = await client.get(f"/api/taxonomy/nodes/{graph['disco'].id}/neighbors")
        assert r.status_code == 200
        items = r.json()["items"]
        assert [(i["label"], i["direction"]) for i in items] == [
            ("house", "influences"),
        ]


class TestRoots:
    async def test_nodes_without_parent(self, client, graph):
        r = await client.get("/api/taxonomy/roots")
        assert r.status_code == 200
        items = r.json()["items"]
        assert [n["label"] for n in items] == ["disco", "electronic music"]
        assert items[0]["wikidataId"] == "Q104817"


class TestStats:
    async def test_counts(self, client, graph):
        r = await client.get("/api/taxonomy/stats")
        assert r.status_code == 200
        assert r.json() == {
            "nodeCount": 4,
            "edgeCount": 3,
            "parentEdgeCount": 2,
            "influenceEdgeCount": 1,
            "rootCount": 2,
        }


class TestListMappings:
    async def test_default(self, client, graph):
        r = await client.get("/api/taxonomy/mappings")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        mapped = next(i for i in data["items"] if i["rawName"] == "Deep House")
        assert mapped["nodeId"] == graph["deep_house"].id
        assert mapped["nodeWikidataId"] == "Q1265336"
        assert mapped["nodeLabel"] == "deep house"

    async def test_unmapped_only(self, client, graph):
        r = await client.get("/api/taxonomy/mappings", params={"unmapped": "true"})
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["rawName"] == "Future Rave"
        assert data["items"][0]["nodeId"] is None


class TestUpdateMapping:
    async def test_requires_auth(self, client, graph):
        r = await client.put(
            f"/api/taxonomy/mappings/{quote('Deep House')}",
            params={"node_id": graph["house"].id},
        )
        assert r.status_code == 401

    async def test_update_existing(self, admin_client, client, graph):
        r = await admin_client.put(
            f"/api/taxonomy/mappings/{quote('Deep House')}",
            params={"node_id": graph["house"].id},
        )
        assert r.status_code == 200
        assert r.json() == {
            "ok": True, "rawName": "Deep House", "nodeId": graph["house"].id,
        }
        listed = (await client.get("/api/taxonomy/mappings")).json()
        mapped = next(i for i in listed["items"] if i["rawName"] == "Deep House")
        assert mapped["nodeId"] == graph["house"].id

    async def test_insert_new(self, admin_client, client, graph):
        r = await admin_client.put(
            f"/api/taxonomy/mappings/{quote('Melodic Techno')}",
            params={"node_id": graph["house"].id},
        )
        assert r.status_code == 200
        assert r.json()["rawName"] == "Melodic Techno"
        listed = (await client.get("/api/taxonomy/mappings")).json()
        assert listed["total"] == 3

    async def test_404_unknown_node(self, admin_client, graph):
        r = await admin_client.put(
            f"/api/taxonomy/mappings/{quote('Deep House')}",
            params={"node_id": 999999},
        )
        assert r.status_code == 404
