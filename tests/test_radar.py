import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("codex_reset_radar", ROOT / "app.py")
RADAR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RADAR)


class TiboSignalTests(unittest.TestCase):
    def test_future_reset_commitment_is_classified_as_reset_related(self):
        result = RADAR.tweet_to_chinese(
            {
                "id": "2091412393368945027",
                "kind": "signal",
                "text": "Reset will land around 14pm PST tomorrow.",
                "at": "2026-08-23T06:29:05Z",
            }
        )

        self.assertEqual("重置相关", result["signal"])
        self.assertIn("即将", result["interpretation_zh"])

    def test_completed_reset_is_not_reopened_by_tomorrows_celebration(self):
        result = RADAR.tweet_to_chinese(
            {
                "id": "2093811840258293947",
                "kind": "signal",
                "text": (
                    "This celebration is moved to tomorrow as the button "
                    "was already pressed today."
                ),
                "at": "2026-08-29T21:23:38Z",
            }
        )

        self.assertEqual("已完成重置", result["signal"])
        self.assertIn("今天已经执行", result["interpretation_zh"])
        self.assertNotIn("即将重置", result["interpretation_zh"])

    def test_forecast_marks_completed_signal_instead_of_future_announcement(self):
        result = RADAR.adjudicate_forecast(
            {
                "mode": "announced",
                "last_reset_at": "2026-08-29T20:43:34Z",
                "probabilities": {
                    "rounded_24h": 25,
                    "rounded_48h": 45,
                    "signal_percent": 93,
                },
                "official_signal": {
                    "at": "2026-08-29T21:23:38Z",
                    "summary": (
                        "This celebration is moved to tomorrow as the button "
                        "was already pressed today."
                    ),
                },
            }
        )

        self.assertEqual("completed", result["mode"])
        self.assertEqual("announced", result["source_mode"])
        self.assertFalse(result["adjudication"]["trusted_announcement"])
        self.assertIn("已经执行", result["adjudication"]["reason_zh"])

    def test_tweet_contains_direct_chinese_content(self):
        result = RADAR.tweet_to_chinese(
            {
                "id": "2102463847714247142",
                "kind": "banked",
                "text": "GPT-6 Sol and Luna are out.",
            }
        )

        self.assertIn("GPT-6 Sol 和 Luna", result["content_zh"])
        self.assertIn("储备重置卡", result["content_zh"])

    def test_feed_selection_skips_irrelevant_first_post_and_caps_at_three(self):
        selected = RADAR.select_tibo_updates(
            [
                {"id": "pizza", "kind": "other", "tibo_lane": "reset_related", "text": "pizza plutot"},
                {"id": "banked", "kind": "banked", "text": "A reset card"},
                {"id": "signal", "kind": "signal", "text": "Reset tomorrow"},
                {"id": "codex", "kind": "codex", "text": "Codex update"},
                {"id": "extra", "kind": "other", "text": "misc"},
            ]
        )

        self.assertEqual(["banked", "signal", "codex"], [item["id"] for item in selected])
        self.assertEqual(3, len(selected))


class RadarPageTests(unittest.TestCase):
    def test_page_renders_official_announcement_instead_of_probability_only(self):
        page = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

        self.assertIn("official_signal", page)
        self.assertIn('f.mode==="announced"', page)
        self.assertIn("官方已宣布", page)

    def test_page_separates_base_probability_from_adjudicated_signal(self):
        page = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

        self.assertIn("未来 48 小时基础概率", page)
        self.assertIn("官方信号置信度", page)
        self.assertIn("signal_percent", page)
        self.assertIn("adjudication", page)
        self.assertIn("已确认当天完成重置", page)
        self.assertIn("Codex 重置历史", page)
        self.assertIn("resetCalendar", page)
        self.assertIn("content_zh", page)
        self.assertIn("tibo-feed", page)


class PublicRadarPayloadTests(unittest.TestCase):
    def test_status_normalizes_model_matrix_health_and_recommendations(self):
        fresh_source = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        result = RADAR.build_model_radar(
            {
                "generated_at": "2026-09-09T06:41:56+08:00",
                "source_updated_at": fresh_source,
                "comprehensive_points": [
                    {"model": "gpt-5.6-sol", "effort": "high", "iq": 98.37, "samples": 86},
                    {"model": "gpt-6-astra", "effort": "medium", "iq": 101.2, "samples": 12},
                ],
                "recommendations": [{"key": "hard_problems", "title": "难题攻坚", "items": [{"model": "gpt-6-astra", "effort": "max", "iq": 103.22}]}],
                "degradation_alerts": {"items": []},
            },
            {
                "source_updated_at": fresh_source,
                "runs_24h_total": 7,
                "runs_48h_total": 92,
                "points": [{"model": "gpt-5.6-sol", "effort": "high", "average_price_usd": 4.2, "average_minutes": 23.5}],
            },
        )

        self.assertEqual("GPT-6 Astra", result["matrix"][0]["model_label"])
        self.assertEqual("GPT-5.6 Sol", result["matrix"][1]["model_label"])
        self.assertEqual(4.2, result["matrix"][1]["average_cost_usd"])
        self.assertEqual(23.5, result["matrix"][1]["average_minutes"])
        self.assertEqual(86, result["health"]["samples"])
        self.assertFalse(result["health"]["stale"])
        self.assertEqual("GPT-6 Astra · max", result["recommendations"][0]["choice"])

    def test_model_labels_include_gpt6_sol_luna_and_preserve_unknown_generations(self):
        self.assertEqual("GPT-6 Sol", RADAR._model_label("gpt-6-sol"))
        self.assertEqual("GPT-6 Luna", RADAR._model_label("gpt-6-luna"))
        self.assertEqual("GPT-7 Astra Minor", RADAR._model_label("gpt-7-astra-minor"))

    def test_model_matrix_accepts_gpt6_rows_from_upstream_without_a_whitelist(self):
        result = RADAR.build_model_radar(
            {
                "source_updated_at": "2099-01-01T00:00:00+00:00",
                "comprehensive_points": [
                    {"model": "gpt-6-sol", "effort": "max", "iq": 110.0, "samples": 2},
                    {"model": "gpt-6-luna", "effort": "high", "iq": 95.0, "samples": 2},
                ],
            },
            {"points": []},
        )

        self.assertEqual(["GPT-6 Sol", "GPT-6 Luna"], [row["model_label"] for row in result["matrix"]])

    def test_status_normalizes_fast_latest_and_history(self):
        result = RADAR.build_fast_radar(
            {
                "updated_at": "2026-08-30T20:15:01+08:00",
                "runs": [
                    {"measured_at": "2026-08-30T20:07:17+08:00", "models": {"astra": {"standard": {"e2e_seconds": 45.0, "ttft_seconds": 8.0, "tps": None}, "fast": {"e2e_seconds": 30.0, "ttft_seconds": 6.0, "tps": None}}}}
                ],
            }
        )

        self.assertEqual(1, result["sample_count"])
        self.assertEqual(1.5, result["latest"][0]["e2e_speedup"])
        self.assertEqual(25.0, result["latest"][0]["ttft_reduction_percent"])
        self.assertIsNone(result["latest"][0]["tps_speedup"])
        self.assertEqual("Astra", result["latest"][0]["model_label"])
        self.assertEqual(1, len(result["history"]["astra"]))

    def test_page_replaces_static_fast_snapshot_with_dynamic_sections(self):
        page = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

        self.assertIn("模型完整矩阵", page)
        self.assertIn("modelNotice", page)
        self.assertIn("GPT-6 Sol", page)
        self.assertIn("GPT-6 Luna", page)
        self.assertIn("暂不复制 5.6 分数冒充新模型", page)
        self.assertIn("降智预警", page)
        self.assertIn("Fast 加速历史", page)
        self.assertIn("数据源健康与模型建议", page)
        self.assertIn("不可测", page)
        self.assertIn('n!==null&&n!==undefined&&n!==""', page)
        self.assertIn("modelName(k)", page)
        self.assertIn("Object.entries(fastRadar.history||{})", page)
        self.assertNotIn("原站 7月30日 09:19 公开页面快照", page)


if __name__ == "__main__":
    unittest.main()
