"""Tune and explain saved-search matching — READ ONLY, NO DATABASE MUTATION.

An engineering/analytics tool (not a production API) that answers:

- "Why did this room match (or not match) this saved search?"
- "What happens if we change the matching weights / threshold?"

It reuses the exact production scoring pipeline
(``savedsearches.services.score_saved_search_match``) with overridable
weights, so what you see here is what the notifier will decide.

Usage examples::

    # Explain one saved search against all of its candidate rooms
    python manage.py tune_saved_search_matching --saved-search-id 3

    # Explain one specific room against a saved search
    python manage.py tune_saved_search_matching --saved-search-id 3 --room-id 42

    # Override weights / threshold for a dry run
    python manage.py tune_saved_search_matching --saved-search-id 3 \\
        --threshold 0.70 --semantic-weight 0.40 --area-weight 0.25 \\
        --price-weight 0.20 --quality-weight 0.15

    # Grid-search a small weight grid (diagnostic mode)
    python manage.py tune_saved_search_matching --saved-search-id 3 --tune

    # Machine-readable output
    python manage.py tune_saved_search_matching --saved-search-id 3 --format json

Safety: the command never writes, updates, or sends notifications. It only
reads the database and prints. ``--tune`` requires ``--room-ids`` (a fixed
candidate set) so it cannot accidentally scan the whole table.
"""

from __future__ import annotations

import itertools
import json

from django.core.management.base import BaseCommand, CommandError

from savedsearches.models import SavedSearch


class Command(BaseCommand):
    help = "Explain and tune saved-search matching (read-only, no DB writes)."

    def add_arguments(self, parser):
        parser.add_argument("--saved-search-id", type=int, required=True)
        parser.add_argument("--room-id", type=int, default=None, help="Explain one specific room.")
        parser.add_argument(
            "--room-ids", type=str, default="", help="Comma-separated room ids for --tune."
        )
        parser.add_argument("--threshold", type=float, default=None)
        parser.add_argument("--area-weight", type=float, default=None)
        parser.add_argument("--price-weight", type=float, default=None)
        parser.add_argument("--room-type-weight", type=float, default=None)
        parser.add_argument("--semantic-weight", type=float, default=None)
        parser.add_argument("--preference-weight", type=float, default=None)
        parser.add_argument("--quality-weight", type=float, default=None)
        parser.add_argument(
            "--tune", action="store_true", help="Grid-search a small weight grid (diagnostic)."
        )
        parser.add_argument("--format", choices=["text", "json"], default="text")

    def handle(self, *args, **options):
        search_id = options["saved_search_id"]
        try:
            search = SavedSearch.objects.select_related("user").get(pk=search_id)
        except SavedSearch.DoesNotExist as err:
            raise CommandError(f"No saved search with id {search_id}") from err

        # ---- build the (possibly overridden) settings ---------------------
        from django.conf import settings

        base_weights = dict(getattr(settings, "SAVED_SEARCH_MATCH_WEIGHTS", {}))
        overrides = {
            "area": options["area_weight"],
            "price": options["price_weight"],
            "room_type": options["room_type_weight"],
            "semantic": options["semantic_weight"],
            "preference": options["preference_weight"],
            "quality": options["quality_weight"],
        }
        weights = {
            key: value if value is not None else base_weights.get(key, 0)
            for key, value in overrides.items()
        }
        threshold = (
            options["threshold"]
            if options["threshold"] is not None
            else float(getattr(settings, "SAVED_SEARCH_MATCH_THRESHOLD", 0.75))
        )

        # ---- pick candidate rooms ------------------------------------------
        from rooms.models import Room

        if options["room_id"] is not None:
            candidate_ids = [options["room_id"]]
        elif options["room_ids"]:
            candidate_ids = [int(x) for x in options["room_ids"].split(",") if x.strip()]
        else:
            candidate_ids = list(
                Room.objects.filter(is_available=True).values_list("id", flat=True)[:20]
            )
        if not candidate_ids:
            raise CommandError(
                "No candidate rooms found (and none given via --room-id / --room-ids)."
            )

        rooms = list(Room.objects.filter(id__in=candidate_ids))
        rooms.sort(key=lambda r: candidate_ids.index(r.id))

        # ---- scoring ---------------------------------------------------------
        from savedsearches.services import score_saved_search_match

        def score_one(room, w, thresh):
            from unittest.mock import patch

            with (
                patch.dict(
                    "savedsearches.services.settings.SAVED_SEARCH_MATCH_WEIGHTS", w, clear=False
                ),
                patch("savedsearches.services.settings.SAVED_SEARCH_MATCH_THRESHOLD", thresh),
            ):
                return score_saved_search_match(search, room)

        results = []
        for room in rooms:
            result = score_one(room, weights, threshold)
            results.append({"room": room, "result": result})

        if options["tune"]:
            self._tune(search, rooms, results, threshold, options)
            return

        if options["format"] == "json":
            self.stdout.write(
                json.dumps(self._to_json(search, results, weights, threshold), indent=2)
            )
        else:
            self._print_text(search, results, weights, threshold)

    # ------------------------------------------------------------------ utils

    def _tune(self, search, rooms, results, threshold, options):
        """Grid-search a small, fixed weight grid in diagnostic mode only.

        Without a labelled dataset we cannot report precision/recall — we
        report the match *rate* under each weight combination so the effect
        of shifting weights is visible, and clearly label it diagnostic.
        """
        grid = {
            "area": [0.20, 0.25, 0.30],
            "price": [0.15, 0.20, 0.25],
            "semantic": [0.15, 0.25, 0.40],
            "quality": [0.10, 0.15],
        }
        rows = []
        for combo in itertools.product(*grid.values()):
            w = dict(zip(grid.keys(), combo, strict=True))
            w["room_type"] = 0.15
            w["preference"] = 0.10
            total = sum(w.values())
            w = {k: round(v / total, 4) for k, v in w.items()}
            matches = 0
            for room in rooms:
                from unittest.mock import patch

                from savedsearches.services import score_saved_search_match

                with (
                    patch.dict(
                        "savedsearches.services.settings.SAVED_SEARCH_MATCH_WEIGHTS", w, clear=False
                    ),
                    patch(
                        "savedsearches.services.settings.SAVED_SEARCH_MATCH_THRESHOLD", threshold
                    ),
                ):
                    result = score_saved_search_match(search, room)
                if result is not None and result["level"] is not None:
                    matches += 1
            rows.append((w, matches / len(rooms)))

        if options["format"] == "json":
            self.stdout.write(
                json.dumps(
                    {
                        "saved_search_id": search.id,
                        "candidate_rooms": len(rooms),
                        "threshold": threshold,
                        "mode": "diagnostic",
                        "note": "No labelled evaluation dataset available; match rate only.",
                        "grid": [{"weights": w, "match_rate": round(rate, 3)} for w, rate in rows],
                    },
                    indent=2,
                )
            )
        else:
            self.stdout.write("READ ONLY - NO DATABASE MUTATION")
            self.stdout.write("")
            self.stdout.write(
                "No labelled evaluation dataset available. Weight tuning is running in "
                "diagnostic mode only (match rate across the given rooms)."
            )
            self.stdout.write("")
            self.stdout.write(
                f"{'Semantic':>10} {'Area':>6} {'Price':>7} {'RoomType':>9} "
                f"{'Quality':>8} {'MatchRate':>10}"
            )
            for w, rate in sorted(rows, key=lambda r: -r[1]):
                self.stdout.write(
                    f"{w['semantic']:>10.2f} {w['area']:>6.2f} {w['price']:>7.2f} "
                    f"{w['room_type']:>9.2f} {w['quality']:>8.2f} {rate:>10.1%}"
                )

    @staticmethod
    def _json_safe(value):
        """Recursively coerce Decimals/other non-JSON types to primitives."""
        from decimal import Decimal

        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, dict):
            return {k: Command._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [Command._json_safe(v) for v in value]
        return value

    def _to_json(self, search, results, weights, threshold):
        return self._json_safe(
            {
                "read_only": True,
                "saved_search_id": search.id,
                "saved_search_name": search.name,
                "filters": search.filters,
                "weights": weights,
                "threshold": threshold,
                "candidates": [
                    {
                        "room_id": item["room"].id,
                        "title": item["room"].title,
                        "area": item["room"].area,
                        "price": item["room"].price,
                        "match": item["result"] is not None and item["result"]["level"] is not None,
                        "score": item["result"]["score"] if item["result"] else None,
                        "level": item["result"]["level"] if item["result"] else None,
                        "category_scores": item["result"]["category_scores"]
                        if item["result"]
                        else None,
                        "hard_filter_failed": item["result"] is None,
                    }
                    for item in results
                ],
            }
        )

    def _print_text(self, search, results, weights, threshold):
        self.stdout.write("READ ONLY - NO DATABASE MUTATION")
        self.stdout.write("")
        self.stdout.write("Saved Search")
        self.stdout.write("--------------------")
        for key, value in (search.filters or {}).items():
            self.stdout.write(f"{key}: {value}")
        self.stdout.write(f"(name: {search.name}, user: {search.user.username})")
        self.stdout.write(f"weights: {weights}")
        self.stdout.write(f"threshold: {threshold}")
        self.stdout.write("")

        for item in results:
            room, result = item["room"], item["result"]
            self.stdout.write("Candidate Room")
            self.stdout.write("--------------------")
            self.stdout.write(f"Room: {room.title}")
            self.stdout.write(f"Price: {room.price}")
            self.stdout.write(f"Area: {room.area}")
            if result is None:
                self.stdout.write("")
                self.stdout.write("NON-MATCH REASONS")
                self.stdout.write("  ✗ Hard filter failed (area/budget/type/gender/verified)")
            else:
                self.stdout.write("")
                self.stdout.write("Scores")
                for cat, score in result["category_scores"].items():
                    self.stdout.write(f"  {cat:>12}: {score:.3f}")
                self.stdout.write("")
                self.stdout.write(f"Final Score: {result['score']}")
                self.stdout.write(f"Threshold:   {threshold}")
                self.stdout.write(
                    f"Result:      {'MATCH' if result['level'] else 'NON-MATCH (below threshold)'}"
                )
                if result["level"]:
                    self.stdout.write("")
                    self.stdout.write("MATCH REASONS")
                    for reason in result["reasons"]:
                        self.stdout.write(f"  ✓ {reason}")
                else:
                    self.stdout.write("")
                    self.stdout.write("NON-MATCH REASONS")
                    self.stdout.write("  ✗ Score below threshold")
            self.stdout.write("")
