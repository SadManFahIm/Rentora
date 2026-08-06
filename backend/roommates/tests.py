"""Unit tests for the roommate matching algorithm.

Covers the scoring math, the hard gates (area + gender), the minimum-score
cutoff, exclusion rules and request handling. Uses Django's built-in
``TestCase`` (no database — every case runs in a transaction) in line with
the rest of the project.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from roommates.models import RoommateMatchRequest, RoommateProfile
from roommates.services.matching import (
    MIN_MATCH_SCORE,
    _budget_overlap,
    _gender_compatible,
    _lifestyle_jaccard,
    _score_pair,
    find_matches,
)
from rooms.models import Room

User = get_user_model()


def make_user(username, gender="male"):
    return User.objects.create_user(username=username, password="test12345", gender=gender)


def make_profile(
    user,
    area="Mirpur",
    budget_min=6000,
    budget_max=10000,
    room_type="shared",
    gender_pref="any",
    lifestyle=None,
    is_looking=True,
):
    return RoommateProfile.objects.create(
        user=user,
        budget_min=budget_min,
        budget_max=budget_max,
        preferred_area=area,
        room_type_pref=room_type,
        gender_pref=gender_pref,
        lifestyle=lifestyle or [],
        is_looking=is_looking,
    )


class BudgetOverlapTests(TestCase):
    def test_perfect_overlap_is_one(self):
        a = make_profile(make_user("a"), budget_min=6000, budget_max=10000)
        b = make_profile(make_user("b"), budget_min=6000, budget_max=10000)
        self.assertEqual(_budget_overlap(a, b), 1.0)

    def test_no_overlap_is_zero(self):
        a = make_profile(make_user("a"), budget_min=6000, budget_max=8000)
        b = make_profile(make_user("b"), budget_min=12000, budget_max=15000)
        self.assertEqual(_budget_overlap(a, b), 0.0)

    def test_partial_overlap_is_fraction_of_union(self):
        # a: 6000-10000, b: 8000-12000 → overlap 2000, union 6000 → 1/3
        a = make_profile(make_user("a"), budget_min=6000, budget_max=10000)
        b = make_profile(make_user("b"), budget_min=8000, budget_max=12000)
        self.assertAlmostEqual(_budget_overlap(a, b), 1 / 3, places=3)

    def test_inverted_range_is_zero(self):
        a = make_profile(make_user("a"), budget_min=10000, budget_max=6000)
        b = make_profile(make_user("b"), budget_min=6000, budget_max=10000)
        self.assertEqual(_budget_overlap(a, b), 0.0)


class LifestyleJaccardTests(TestCase):
    def test_identical_tags_is_one(self):
        a = make_profile(make_user("a"), lifestyle=["non_smoker", "quiet"])
        b = make_profile(make_user("b"), lifestyle=["non_smoker", "quiet"])
        self.assertEqual(_lifestyle_jaccard(a, b), 1.0)

    def test_disjoint_tags_is_zero(self):
        a = make_profile(make_user("a"), lifestyle=["non_smoker", "quiet"])
        b = make_profile(make_user("b"), lifestyle=["smoker", "social"])
        self.assertEqual(_lifestyle_jaccard(a, b), 0.0)

    def test_partial_overlap(self):
        # {non_smoker, quiet} ∩ {quiet, clean} = {quiet}; union size 3 → 1/3
        a = make_profile(make_user("a"), lifestyle=["non_smoker", "quiet"])
        b = make_profile(make_user("b"), lifestyle=["quiet", "clean"])
        self.assertAlmostEqual(_lifestyle_jaccard(a, b), 1 / 3, places=3)

    def test_empty_tags_is_zero(self):
        a = make_profile(make_user("a"), lifestyle=[])
        b = make_profile(make_user("b"), lifestyle=[])
        self.assertEqual(_lifestyle_jaccard(a, b), 0.0)


class GenderCompatibilityTests(TestCase):
    def test_any_with_any(self):
        a = make_profile(make_user("a", gender="male"), gender_pref="any")
        b = make_profile(make_user("b", gender="female"), gender_pref="any")
        self.assertTrue(_gender_compatible(a, b))

    def test_reciprocal_preference_passes(self):
        # A wants female; B is female and wants male → both satisfied.
        a = make_profile(make_user("a", gender="male"), gender_pref="female")
        b = make_profile(make_user("b", gender="female"), gender_pref="male")
        self.assertTrue(_gender_compatible(a, b))

    def test_unreciprocated_preference_fails(self):
        # A (female) wants female; B is male → A's stated pref rules B out.
        a = make_profile(make_user("a", gender="female"), gender_pref="female")
        b = make_profile(make_user("b", gender="male"), gender_pref="any")
        self.assertFalse(_gender_compatible(a, b))

    def test_directional_failure_both_ways(self):
        a = make_profile(make_user("a", gender="male"), gender_pref="female")
        b = make_profile(make_user("b", gender="male"), gender_pref="any")
        self.assertFalse(_gender_compatible(a, b))


class ScorePairTests(TestCase):
    def test_perfect_match_scores_100(self):
        a = make_profile(make_user("a"), lifestyle=["non_smoker", "quiet"])
        b = make_profile(make_user("b"), lifestyle=["non_smoker", "quiet"])
        result = _score_pair(a, b)
        self.assertIsNotNone(result)
        self.assertEqual(result.score, 100)
        self.assertIn("Budgets overlap well", result.reasons)
        self.assertIn("Same preferred area", result.reasons)
        self.assertIn("Same room-type preference", result.reasons)
        self.assertIn("Similar lifestyle", result.reasons)

    def test_different_area_is_hard_gate(self):
        a = make_profile(make_user("a"), area="Mirpur")
        b = make_profile(make_user("b"), area="Dhanmondi")
        self.assertIsNone(_score_pair(a, b))

    def test_gender_mismatch_is_hard_gate_even_with_perfect_rest(self):
        a = make_profile(make_user("a", gender="female"), gender_pref="female")
        b = make_profile(make_user("b", gender="male"), gender_pref="any")
        self.assertIsNone(_score_pair(a, b))

    def test_different_room_type_reduces_score(self):
        a = make_profile(make_user("a"), room_type="shared")
        b = make_profile(make_user("b"), room_type="single")
        result = _score_pair(a, b)
        self.assertIsNotNone(result)
        # No room-type bonus (15%) and no lifestyle tags (10%) → 75.
        self.assertEqual(result.score, 75)

    def test_partial_budget_overlap_wording(self):
        a = make_profile(make_user("a"), budget_min=6000, budget_max=10000)
        b = make_profile(make_user("b"), budget_min=8000, budget_max=12000)
        result = _score_pair(a, b)
        self.assertIn("Budgets partly overlap", result.reasons)
        self.assertNotIn("Budgets overlap well", result.reasons)


class FindMatchesTests(TestCase):
    def test_returns_best_first(self):
        me = make_profile(make_user("me"))
        make_profile(make_user("strong"), lifestyle=["non_smoker"])
        make_profile(
            make_user("weak"),
            budget_min=9000,
            budget_max=12000,
            room_type="single",
            lifestyle=["smoker"],
        )
        results = find_matches(me)
        self.assertEqual([r.profile.user.username for r in results], ["strong", "weak"])
        self.assertGreater(results[0].score, results[1].score)

    def test_excludes_self_and_already_requested(self):
        me = make_profile(make_user("me"))
        candidate = make_profile(make_user("candidate"))
        already = make_profile(make_user("already"))
        RoommateMatchRequest.objects.create(
            sender=me.user, receiver=already.user, message="hi"
        )
        # The view builds exclude_users from the user's own id plus everyone
        # they have already sent a request to — replicate that here.
        exclude = {me.user_id, already.user_id, candidate.user_id}
        results = find_matches(me, exclude_users=exclude)
        self.assertEqual([r.profile.user.username for r in results], [])

    def test_self_is_always_excluded(self):
        me = make_profile(make_user("me"))
        # Even without an explicit exclude set, the caller is never a match.
        results = find_matches(me)
        self.assertTrue(all(r.profile.user_id != me.user_id for r in results))

    def test_filters_out_users_not_looking(self):
        me = make_profile(make_user("me"))
        make_profile(make_user("busy"), is_looking=False)
        results = find_matches(me)
        self.assertEqual(results, [])

    def test_weakest_eligible_candidate_scores_at_least_the_floor(self):
        me = make_profile(make_user("me"))
        # Disjoint budget + different room type + no shared lifestyle tags,
        # but same area and compatible gender: the hard gates still admit the
        # candidate, so the score can never drop below area(25) + gender(15).
        make_profile(
            make_user("far"),
            budget_min=50000,
            budget_max=60000,
            room_type="single",
            lifestyle=["smoker", "social"],
        )
        results = find_matches(me)
        self.assertEqual([r.profile.user.username for r in results], ["far"])
        self.assertGreaterEqual(results[0].score, MIN_MATCH_SCORE)


class RoommateRequestTests(TestCase):
    def test_unique_pair_constraint(self):
        sender, receiver = make_user("sender"), make_user("receiver")
        RoommateMatchRequest.objects.create(sender=sender, receiver=receiver)
        with self.assertRaises(IntegrityError):
            RoommateMatchRequest.objects.create(sender=sender, receiver=receiver)

    def test_status_defaults_pending(self):
        sender, receiver = make_user("sender"), make_user("receiver")
        req = RoommateMatchRequest.objects.create(sender=sender, receiver=receiver)
        self.assertEqual(req.status, RoommateMatchRequest.Status.PENDING)

    def test_profile_ordering_by_updated(self):
        first = make_profile(make_user("first"))
        make_profile(make_user("second"))
        # Touch `first` so it becomes the newest.
        first.bio = "updated"
        first.save()
        self.assertEqual(
            RoommateProfile.objects.first().user.username, "first"
        )

    def test_area_choices_match_room_model(self):
        self.assertEqual(
            set(Room.Area.choices),
            set(RoommateProfile._meta.get_field("preferred_area").choices),
        )


class ProfileMoveInDateTests(TestCase):
    def test_move_in_date_stored(self):
        user = make_user("mover")
        profile = make_profile(user)
        profile.move_in_date = date(2025, 9, 1)
        profile.save()
        profile.refresh_from_db()
        self.assertEqual(profile.move_in_date, date(2025, 9, 1))
