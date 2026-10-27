import asyncio
import json
import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from travel_agent.config import environment
from travel_agent.schemas import TripConstraints
from travel_agent.tools import build_tools


class TavilyConfigTests(unittest.TestCase):
    def test_dotenv_alias_is_available_under_canonical_name(self):
        with (
            patch(
                "travel_agent.config.dotenv_values",
                return_value={"TAVILY": "fixture-key"},
            ),
            patch.dict(os.environ, {}, clear=True),
        ):
            self.assertEqual(environment()["TAVILY_API_KEY"], "fixture-key")

    def test_canonical_key_wins_and_empty_placeholder_uses_alias(self):
        for canonical, expected in [
            ("canonical-key", "canonical-key"),
            ("", "alias-key"),
        ]:
            with self.subTest(canonical=canonical):
                with (
                    patch(
                        "travel_agent.config.dotenv_values",
                        return_value={
                            "TAVILY": "alias-key",
                            "TAVILY_API_KEY": canonical,
                        },
                    ),
                    patch.dict(os.environ, {}, clear=True),
                ):
                    self.assertEqual(environment()["TAVILY_API_KEY"], expected)

    def test_environment_alias_overrides_dotenv_alias(self):
        with (
            patch(
                "travel_agent.config.dotenv_values", return_value={"TAVILY": "file-key"}
            ),
            patch.dict(os.environ, {"TAVILY": "process-key"}, clear=True),
        ):
            self.assertEqual(environment()["TAVILY_API_KEY"], "process-key")


class TavilyToolsTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_roles_search_extract_and_store_sources_with_alias(self):
        for role in ("transport", "stays", "experience"):
            with self.subTest(role=role):
                requests = []

                def handle(request):
                    requests.append(request)
                    self.assertEqual(
                        request.headers["Authorization"], "Bearer fixture-key"
                    )
                    body = json.loads(request.content)
                    if request.url.path == "/search":
                        self.assertFalse(body["include_answer"])
                        return httpx.Response(
                            200,
                            json={
                                "results": [
                                    {
                                        "url": "https://example.com/sochi",
                                        "title": "Сочи",
                                        "content": "Краткая справка об отеле и районе.",
                                    }
                                ]
                            },
                        )
                    self.assertEqual(body["urls"], ["https://example.com/sochi"])
                    return httpx.Response(
                        200,
                        json={
                            "results": [
                                {
                                    "url": "https://example.com/sochi",
                                    "raw_content": "Подробное содержимое страницы из Extract.",
                                }
                            ]
                        },
                    )

                with (
                    patch(
                        "travel_agent.config.dotenv_values",
                        return_value={"TAVILY": "fixture-key"},
                    ),
                    patch.dict(os.environ, {}, clear=True),
                ):
                    env = environment()
                evidence, sources = {}, []
                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(handle)
                ) as client:
                    tools = {
                        t.name: t
                        for t in build_tools(
                            role,
                            TripConstraints(),
                            0,
                            client,
                            env,
                            evidence,
                            [],
                            {"tools": 0},
                            web_evidence=sources,
                        )
                    }
                    loop = asyncio.get_running_loop()
                    with (
                        patch(
                            "travel_agent.tools.runtime_call", new=AsyncMock()
                        ) as mcp,
                        patch.object(
                            loop,
                            "getaddrinfo",
                            new=AsyncMock(
                                return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]
                            ),
                        ),
                    ):
                        search = await tools["tavily_search"].ainvoke({"query": "Сочи"})
                        extract = await tools["tavily_extract"].ainvoke(
                            {"selected_urls": [search["results"][0]["url"]]}
                        )
                        mcp.assert_not_called()
                self.assertEqual(extract["status"], "ok")
                self.assertEqual(
                    sources[-1].text, "Подробное содержимое страницы из Extract."
                )
                self.assertEqual(
                    [r.url.path for r in requests], ["/search", "/extract"]
                )
                self.assertTrue(
                    all(
                        c.price is None and c.source.evidence == "catalog"
                        for c in evidence.values()
                    )
                )
                self.assertNotIn(
                    "fixture-key",
                    json.dumps([s.model_dump(mode="json") for s in sources]),
                )

    async def test_extract_blocks_unseen_urls_before_network(self):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: self.fail("Unexpected network")
            )
        ) as client:
            tools = {
                t.name: t
                for t in build_tools(
                    "experience",
                    TripConstraints(),
                    0,
                    client,
                    {"TAVILY_API_KEY": "fixture-key"},
                    {},
                    [],
                    {"tools": 0},
                )
            }
            result = await tools["tavily_extract"].ainvoke(
                {"selected_urls": ["https://example.com/not-searched"]}
            )
        self.assertEqual(result["status"], "forbidden")

    async def test_dns_timeout_skips_only_unreachable_search_result(self):
        seen = []

        def handle(request):
            if request.url.path == "/search":
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {"url": "https://slow.example.com/page", "content": "One"},
                            {"url": "https://example.com/page", "content": "Two"},
                        ]
                    },
                )
            seen.extend(json.loads(request.content)["urls"])
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "url": "https://example.com/page",
                            "raw_content": "Valid page content",
                        }
                    ]
                },
            )

        warnings = []
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            tools = {
                t.name: t
                for t in build_tools(
                    "experience",
                    TripConstraints(),
                    0,
                    client,
                    {"TAVILY_API_KEY": "fixture-key"},
                    {},
                    warnings,
                    {"tools": 0},
                )
            }
            await tools["tavily_search"].ainvoke({"query": "Сочи"})
            with patch.object(
                asyncio.get_running_loop(),
                "getaddrinfo",
                new=AsyncMock(
                    side_effect=[TimeoutError, [(2, 1, 6, "", ("93.184.216.34", 443))]]
                ),
            ):
                result = await tools["tavily_extract"].ainvoke(
                    {
                        "selected_urls": [
                            "https://slow.example.com/page",
                            "https://example.com/page",
                        ]
                    }
                )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(seen, ["https://example.com/page"])
        self.assertEqual(
            result["skipped_urls"],
            [{"url": "https://slow.example.com/page", "status": "timeout"}],
        )
        self.assertIn("tavily:dns_timeout", warnings)

    async def test_private_dns_address_is_blocked_before_extract_request(self):
        requests = []

        def handle(request):
            requests.append(request.url.path)
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"url": "https://example.com/page", "content": "Search result"}
                    ]
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            tools = {
                t.name: t
                for t in build_tools(
                    "experience",
                    TripConstraints(),
                    0,
                    client,
                    {"TAVILY_API_KEY": "fixture-key"},
                    {},
                    [],
                    {"tools": 0},
                )
            }
            await tools["tavily_search"].ainvoke({"query": "Сочи"})
            with patch.object(
                asyncio.get_running_loop(),
                "getaddrinfo",
                new=AsyncMock(return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]),
            ):
                result = await tools["tavily_extract"].ainvoke(
                    {"selected_urls": ["https://example.com/page"]}
                )
        self.assertEqual(result["status"], "forbidden")
        self.assertEqual(requests, ["/search"])
