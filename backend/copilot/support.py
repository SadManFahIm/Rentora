"""AI Support Copilot (Phase 15 — B2).

A deterministic, LLM-free support assistant over a curated bilingual
(EN + BN) help corpus. Retrieval is keyword-overlap scoring over the
corpus docs; answers are pre-written, human-reviewed text — optionally
rendered with *live platform facts* (tier prices, deposit policy, ...)
pulled from Django settings/models at request time, so the answer is
always grounded in the real product.

Honesty contract (same as the Copilot chat): the assistant answers only
from the corpus. A question it cannot match gets a transparent fallback
(``grounded: false``) instead of a made-up answer, and it never claims
actions it cannot take (it does not cancel bookings, change prices, or
contact admins — it tells the user how to do those things).
"""

from __future__ import annotations

import re

from django.conf import settings

# ---------------------------------------------------------------------------
# Corpus. Each doc: topic key, bilingual titles, retrieval keywords (EN+BN,
# matched case-insensitively as substrings), and a human-written answer.
# ``dynamic`` docs are rendered with live facts at request time.
# ---------------------------------------------------------------------------

SUPPORT_DOCS: list[dict] = [
    {
        "topic": "listing_howto",
        "title": "How to list a room",
        "title_bn": "কীভাবে রুম লিস্ট করবেন",
        "keywords": [
            "list",
            "listing",
            "post a room",
            "add room",
            "advertise",
            "লিস্ট",
            "রুম পোস্ট",
            "পোস্ট করব",
            "বিজ্ঞাপন",
            "রুম দেব",
        ],
        "answer": (
            "To list a room: log in, open the dashboard and pick “Add "
            "Listing”. Fill in the details (area, rent, room type, photos, "
            "amenities) and publish. New listings start on the Free tier; "
            "Featured (৳199/30 days) and Premium (৳499/30 days) promotions "
            "raise visibility. Make sure your NID is verified — verified "
            "landlords get a trust badge that tenants look for."
        ),
        "answer_bn": (
            "রুম লিস্ট করতে: লগ ইন করে ড্যাশবোর্ড থেকে “Add Listing” বেছে নিন। "
            "বিস্তারিত তথ্য দিন (এলাকা, ভাড়া, রুমের ধরন, ছবি, সুবিধা) আর "
            "পাবলিশ করুন। নতুন লিস্টিং Free টিয়ারে শুরু হয়; Featured "
            "(৳১৯৯/৩০ দিন) এবং Premium (৳৪৯৯/৩০ দিন) প্রমোশনে বেশি মানুষ "
            "দেখে। NID ভেরিফায়েড রাখুন — ভেরিফায়েড বাড়িওয়ালারা ট্রাস্ট "
            "ব্যাজ পান, যা ভাড়াটিয়ারা খোঁজেন।"
        ),
    },
    {
        "topic": "pricing_tiers",
        "title": "Listing promotion tiers",
        "title_bn": "লিস্টিং প্রমোশন টিয়ার",
        "keywords": [
            "tier",
            "promotion",
            "featured",
            "premium",
            "boost",
            "visibility",
            "টিয়ার",
            "প্রমোশন",
            "ফিচার্ড",
            "প্রিমিয়াম",
            "বুস্ট",
        ],
        "answer": (
            "Listings start Free. Featured and Premium promotions last "
            "{tier_days} days and cost: {tier_prices}. Promoted listings rank "
            "higher in search and the map. You can buy a promotion from your "
            "listing dashboard; payment goes through the platform's payment "
            "gateway (SSLCommerz / bKash)."
        ),
        "answer_bn": (
            "লিস্টিং Free টিয়ারে শুরু হয়। Featured আর Premium প্রমোশন "
            "{tier_days} দিন থাকে, দাম: {tier_prices}। প্রমোটেড লিস্টিং "
            "সার্চ আর ম্যাপে উপরে দেখায়। লিস্টিং ড্যাশবোর্ড থেকে প্রমোশন "
            "কিনতে পারবেন; পেমেন্ট প্ল্যাটফর্মের গেটওয়েতে (SSLCommerz / "
            "bKash) হয়।"
        ),
        "dynamic": True,
    },
    {
        "topic": "booking_howto",
        "title": "How booking works",
        "title_bn": "বুকিং কীভাবে কাজ করে",
        "keywords": [
            "booking",
            "book",
            "reserve",
            "apply",
            "বুকিং",
            "বুক",
            "আবেদন",
            "রুম নিব",
        ],
        "answer": (
            "Booking is request-based: send a booking request on a listing, "
            "the landlord approves it, and the rent follows the listing's "
            "price. A security deposit (set by the landlord, shown on the "
            "listing) may be required — it's tracked in your booking and "
            "refunded when the lease ends. You can message the landlord "
            "first through the in-app chat to confirm details."
        ),
        "answer_bn": (
            "বুকিং রিকোয়েস্ট ভিত্তিক: লিস্টিংয়ে বুকিং রিকোয়েস্ট পাঠান, "
            "বাড়িওয়ালা অনুমোদন করেন, ভাড়া লিস্টিংয়ের দাম অনুযায়ী হয়। "
            "সিকিউরিটি ডিপোজিট (বাড়িওয়ালা নির্ধারণ করেন, লিস্টিংয়ে দেখা "
            "যায়) লাগতে পারে — বুকিংয়ে ট্র্যাক করা হয়, লিজ শেষে রিফান্ড "
            "হয়। আগে ইন-অ্যাপ চ্যাটে বাড়িওয়ালার সাথে কথা বলে নিশ্চিত "
            "হয়ে নিতে পারেন।"
        ),
    },
    {
        "topic": "security_deposit",
        "title": "Security deposit",
        "title_bn": "সিকিউরিটি ডিপোজিট",
        "keywords": [
            "deposit",
            "security deposit",
            "advance",
            "jama",
            "ডিপোজিট",
            "সিকিউরিটি",
            "জমা",
            "আগাম",
        ],
        "answer": (
            "The security deposit amount is set by the landlord and shown on "
            "the listing before you book. The platform tracks its paid and "
            "refunded state inside the booking. If a deposit is unpaid and "
            "required, the booking stays pending until it clears. Never pay "
            "any deposit outside the platform — paying a stranger off-app "
            "is the #1 scam vector; keep everything in Rentora chat and "
            "payments."
        ),
        "answer_bn": (
            "সিকিউরিটি ডিপোজিটের পরিমাণ বাড়িওয়ালা ঠিক করেন এবং বুকিংয়ের "
            "আগে লিস্টিংয়ে দেখা যায়। প্ল্যাটফর্ম বুকিংয়ের ভেতরে এর পেইড "
            "আর রিফান্ড অবস্থা ট্র্যাক করে। ডিপোজিট দেওয়া না থাকলে বুকিং "
            "পেন্ডিং থাকে। প্ল্যাটফর্মের বাইরে কাউকে ডিপোজিট দেবেন না — "
            "অ্যাপের বাইরে টাকা পাঠানোই সবচেয়ে বড় স্ক্যাম ভেক্টর; সবকিছু "
            "Rentora চ্যাট আর পেমেন্টে রাখুন।"
        ),
    },
    {
        "topic": "payments",
        "title": "Payments on Rentora",
        "title_bn": "Rentora-তে পেমেন্ট",
        "keywords": [
            "pay",
            "payment",
            "bkash",
            "nagad",
            "sslcommerz",
            "card",
            "gateway",
            "পেমেন্ট",
            "পে",
            "বিকাশ",
            "নগদ",
            "কার্ড",
        ],
        "answer": (
            "Payments go through the platform's gateway — SSLCommerz and "
            "bKash — for booking deposits, rents and listing promotions. "
            "Payments outside the platform are not protected: if anyone asks "
            "you to send money by another route (Western Union, a personal "
            "bKash number, an off-app link), stop and report them from the "
            "chat."
        ),
        "answer_bn": (
            "পেমেন্ট প্ল্যাটফর্মের গেটওয়ে দিয়ে হয় — SSLCommerz আর bKash — "
            "বুকিং ডিপোজিট, ভাড়া আর লিস্টিং প্রমোশনের জন্য। প্ল্যাটফর্মের "
            "বাইরের পেমেন্ট সুরক্ষিত নয়: কেউ অন্য পথে টাকা পাঠাতে বললে "
            "(ওয়েস্টার্ন ইউনিয়ন, ব্যক্তিগত বিকাশ নম্বর, বাইরের লিংক) থামুন "
            "আর চ্যাট থেকে রিপোর্ট করুন।"
        ),
    },
    {
        "topic": "refund",
        "title": "Refunds",
        "title_bn": "রিফান্ড",
        "keywords": [
            "refund",
            "return money",
            "money back",
            "রিফান্ড",
            "টাকা ফেরত",
            "টাকা ফেরত পাব",
        ],
        "answer": (
            "Security deposits are refunded when the lease ends per the "
            "booking terms. If you paid something and it wasn't delivered "
            "(e.g. a booking that never got approved), open a dispute from "
            "the booking or contact support with the payment reference. "
            "Legitimate refunds never require an upfront 'processing fee' — "
            "that request is a scam."
        ),
        "answer_bn": (
            "লিজ শেষে সিকিউরিটি ডিপোজিট বুকিংয়ের শর্ত অনুযায়ী ফেরত হয়। "
            "কিছু পেমেন্ট ডেলিভার না হলে (যেমন অনুমোদন না হওয়া বুকিং) "
            "বুকিং থেকে ডিসপিউট খুলুন বা পেমেন্ট রেফারেন্সসহ সাপোর্টে "
            "যোগাযোগ করুন। বৈধ রিফান্ডে কখনো আগে 'প্রসেসিং ফি' লাগে না — "
            "সেই অনুরোধ স্ক্যাম।"
        ),
    },
    {
        "topic": "kyc",
        "title": "NID verification (KYC)",
        "title_bn": "NID ভেরিফিকেশন (KYC)",
        "keywords": [
            "kyc",
            "nid",
            "verify",
            "verification",
            "id card",
            "identity",
            "কেওয়াইসি",
            "এনআইডি",
            "ভেরিফিকেশন",
            "আইডি",
        ],
        "answer": (
            "Upload your NID from Profile → KYC. The document goes through "
            "an automatic pre-screen (format, duplicate check, fraud "
            "signals) and an admin review. Once approved you get the "
            "verified badge — it's the strongest trust signal for both "
            "landlords and tenants. Your document is only used for "
            "verification, never shared in chat."
        ),
        "answer_bn": (
            "প্রোফাইল → KYC থেকে NID আপলোড করুন। ডকুমেন্টটি অটোমেটিক "
            "প্রি-স্ক্রিনে যায় (ফরম্যাট, ডুপ্লিকেট চেক, ফ্রড সিগনাল) আর "
            "অ্যাডমিন রিভিউতে যায়। অনুমোদন হলে ভেরিফায়েড ব্যাজ পাবেন — "
            "বাড়িওয়ালা আর ভাড়াটিয়া দু'পক্ষের জন্য এটাই সবচেয়ে শক্তিশালী "
            "ট্রাস্ট সিগনাল। ডকুমেন্ট শুধু ভেরিফিকেশনে ব্যবহার হয়, চ্যাটে "
            "কখনো শেয়ার হয় না।"
        ),
    },
    {
        "topic": "chat_safety",
        "title": "Chat safety",
        "title_bn": "চ্যাট নিরাপত্তা",
        "keywords": [
            "safety",
            "scam",
            "fraud",
            "suspicious",
            "blocked message",
            "নিরাপত্তা",
            "স্ক্যাম",
            "ফ্রড",
            "সন্দেহজনক",
            "মেসেজ ব্লক",
        ],
        "answer": (
            "Every chat message passes a safety engine that detects payment "
            "redirects, advance-payment pressure, phishing links, "
            "impersonation and credential requests. Risky messages are "
            "warned (you see a caution), flagged for admin review, or "
            "blocked entirely. A blocked message is never stored. If you "
            "see a warning, trust it — verify everything in-app before "
            "sending money or documents."
        ),
        "answer_bn": (
            "প্রতিটি চ্যাট মেসেজ একটি সেফটি ইঞ্জিন দিয়ে যায়, যা পেমেন্ট "
            "রিডাইরেক্ট, আগাম টাকার চাপ, ফিশিং লিংক, ভুয়া পরিচয় আর "
            "ক্রেডেনশিয়াল চাওয়া শনাক্ত করে। ঝুঁকিপূর্ণ মেসেজে সতর্কতা "
            "(কশন), অ্যাডমিন রিভিউ ফ্ল্যাগ, বা পুরো ব্লক হয়। ব্লক করা "
            "মেসেজ কখনো সংরক্ষিত হয় না। সতর্কতা দেখলে বিশ্বাস করুন — "
            "টাকা বা ডকুমেন্ট পাঠানোর আগে সবকিছু অ্যাপের ভেতরে যাচাই করুন।"
        ),
    },
    {
        "topic": "report_block",
        "title": "Report or block a user",
        "title_bn": "ইউজার রিপোর্ট বা ব্লক",
        "keywords": [
            "report",
            "block",
            "harass",
            "impersonat",
            "spam",
            "রিপোর্ট",
            "ব্লক",
            "হয়রানি",
            "স্প্যাম",
        ],
        "answer": (
            "From any chat: use the report option (categories include scam, "
            "harassment, fake listing, payment fraud, impersonation, spam) "
            "and/or block the user. Reports go to the admin moderation "
            "queue and every action is audited. Blocking closes the "
            "conversation for both sides. You can also report a specific "
            "suspicious message."
        ),
        "answer_bn": (
            "যেকোনো চ্যাট থেকে: রিপোর্ট অপশন ব্যবহার করুন (ক্যাটাগরি: "
            "স্ক্যাম, হয়রানি, ভুয়া লিস্টিং, পেমেন্ট ফ্রড, ভুয়া পরিচয়, "
            "স্প্যাম) এবং/অথবা ইউজার ব্লক করুন। রিপোর্ট অ্যাডমিন মডারেশন "
            "কিউতে যায়, প্রতিটি সিদ্ধান্ত অডিট হয়। ব্লক করলে দু'পক্ষের "
            "কথোপকথন বন্ধ হয়। নির্দিষ্ট সন্দেহজনক মেসেজও রিপোর্ট করতে "
            "পারবেন।"
        ),
    },
    {
        "topic": "fraud",
        "title": "Fraud protection",
        "title_bn": "ফ্রড সুরক্ষা",
        "keywords": [
            "fraud",
            "fake listing",
            "fake photo",
            "scam listing",
            "ফ্রড",
            "ভুয়া লিস্টিং",
            "ভুয়া ছবি",
        ],
        "answer": (
            "The platform runs a fraud engine over listings: duplicate "
            "photos, suspicious prices, cross-listing patterns and owner "
            "risk signals. Risky listings are demoted in ranking and can "
            "be hidden by moderators. There is no foolproof system — if a "
            "deal looks too good, verify the landlord's identity, visit the "
            "room first, and never pay before a signed agreement."
        ),
        "answer_bn": (
            "প্ল্যাটফর্মে লিস্টিংয়ের ওপর ফ্রড ইঞ্জিন চলে: ডুপ্লিকেট ছবি, "
            "সন্দেহজনক দাম, ক্রস-লিস্টিং প্যাটার্ন আর মালিকের রিস্ক "
            "সিগনাল। ঝুঁকিপূর্ণ লিস্টিং র্যাংকিংয়ে নিচে নামে, মডারেটর "
            "লুকাতেও পারেন। নিখুঁত সিস্টেম নেই — ডিল খুব ভালো লাগলে মালিকের "
            "পরিচয় যাচাই করুন, আগে রুম দেখুন, আর স্বাক্ষরিত চুক্তির আগে "
            "কখনো টাকা দেবেন না।"
        ),
    },
    {
        "topic": "saved_searches",
        "title": "Saved searches & alerts",
        "title_bn": "সেভড সার্চ ও অ্যালার্ট",
        "keywords": [
            "saved search",
            "alert",
            "notification",
            "email",
            "digest",
            "সেভড সার্চ",
            "অ্যালার্ট",
            "নোটিফিকেশন",
            "ইমেইল",
        ],
        "answer": (
            "Save a search with your filters (area, budget, type, verified "
            "only) and the AI matcher emails you when matching rooms appear "
            "or a saved room's price drops. You'll also get periodic digest "
            "emails summarising new matches. Manage them from Dashboard → "
            "Saved searches; unsubscribe anytime from the email itself."
        ),
        "answer_bn": (
            "ফিল্টারসহ সার্চ সেভ করুন (এলাকা, বাজেট, ধরন, শুধু ভেরিফায়েড) — "
            "AI ম্যাচার মিলে যাওয়া রুম বা দাম কমলে ইমেইল পাঠায়। পর্যায়ক্রমে "
            "নতুন ম্যাচের ডাইজেস্ট ইমেইলও পাবেন। ড্যাশবোর্ড → Saved searches "
            "থেকে ম্যানেজ করুন; ইমেইল থেকেই যেকোনো সময় আনসাবস্ক্রাইব।"
        ),
    },
    {
        "topic": "referral",
        "title": "Referral program",
        "title_bn": "রেফারেল প্রোগ্রাম",
        "keywords": [
            "referral",
            "invite",
            "friend",
            "share code",
            "ref",
            "রেফারেল",
            "ইনভাইট",
            "বন্ধু",
            "কোড শেয়ার",
        ],
        "answer": (
            "Every account has a referral code. Share your link (Dashboard → "
            "Referral); when a friend registers with it, they're linked to "
            "you and you can track invited users in your referral stats. "
            "It's the easiest way to help someone find a place you know "
            "and trust."
        ),
        "answer_bn": (
            "প্রতিটি অ্যাকাউন্টে একটি রেফারেল কোড থাকে। আপনার লিংক শেয়ার "
            "করুন (ড্যাশবোর্ড → Referral); বন্ধু সেটা দিয়ে রেজিস্টার করলে "
            "তিনি আপনার সাথে লিংক হন আর রেফারেল স্ট্যাটসে আমন্ত্রিতদের "
            "দেখতে পারেন।"
        ),
    },
    {
        "topic": "disputes",
        "title": "Disputes",
        "title_bn": "ডিসপিউট",
        "keywords": [
            "dispute",
            "complaint",
            "issue with booking",
            "deposit not returned",
            "ডিসপিউট",
            "অভিযোগ",
            "ডিপোজিট ফেরত না",
        ],
        "answer": (
            "If something goes wrong with a booking (deposit not returned, "
            "unexpected charges, listing differs from reality), open a "
            "dispute from the booking with photos and messages as evidence. "
            "Admins review both sides and the outcome is audited. Keep "
            "evidence in-app: chat history and booking records are the "
            "strongest proof."
        ),
        "answer_bn": (
            "বুকিংয়ে সমস্যা হলে (ডিপোজিট ফেরত না আসা, হঠাৎ চার্জ, লিস্টিং "
            "আসল থেকে আলাদা) বুকিং থেকে ডিসপিউট খুলুন, ছবি ও মেসেজ প্রমাণ "
            "সহ। অ্যাডমিনরা দু'পক্ষই দেখে, ফলাফল অডিট হয়। প্রমাণ অ্যাপের "
            "ভেতরে রাখুন: চ্যাট ইতিহাস আর বুকিং রেকর্ডই সবচেয়ে শক্ত প্রমাণ।"
        ),
    },
    {
        "topic": "agreement",
        "title": "Rental agreement",
        "title_bn": "ভাড়ার চুক্তি",
        "keywords": [
            "agreement",
            "contract",
            "lease",
            "paper",
            "documents needed",
            "চুক্তি",
            "কন্ট্রাক্ট",
            "লিজ",
            "ডকুমেন্ট",
        ],
        "answer": (
            "Typical documents: a copy of your NID and one month's advance. "
            "The platform has an AI agreement checker — paste the agreement "
            "text and it highlights clauses and missing points before you "
            "sign. It's a first-pass review, not legal advice: for large "
            "amounts, have a lawyer read it."
        ),
        "answer_bn": (
            "সাধারণত লাগে: NID-র কপি আর এক মাসের অগ্রিম। প্ল্যাটফর্মে AI "
            "চুক্তি চেকার আছে — চুক্তির লেখা পেস্ট করলে স্বাক্ষরের আগে "
            "ধারা আর ঘাটতি দেখায়। এটা প্রথম-ধাপের রিভিউ, আইনি পরামর্শ নয়: "
            "বড় অংকের জন্য আইনজীবী দিয়ে পড়ান।"
        ),
    },
    {
        "topic": "contact_support",
        "title": "Contacting support",
        "title_bn": "সাপোর্টে যোগাযোগ",
        "keywords": [
            "support",
            "help",
            "human",
            "agent",
            "customer service",
            "সাপোর্ট",
            "সাহায্য",
            "কাস্টমার কেয়ার",
        ],
        "answer": (
            "If the Copilot can't answer your question, ask here in Bangla "
            "or English — it searches the help library. For account or "
            "payment issues, open a dispute/report from the relevant page "
            "so an admin sees the full context. Never share OTPs, "
            "passwords or payment PINs with anyone, including people "
            "claiming to be support."
        ),
        "answer_bn": (
            "Copilot উত্তর দিতে না পারলে বাংলা বা ইংরেজিতে এখানে জিজ্ঞেস "
            "করুন — এটি হেল্প লাইব্রেরি খোঁজে। অ্যাকাউন্ট বা পেমেন্ট "
            "সমস্যায় সংশ্লিষ্ট পেজ থেকে ডিসপিউট/রিপোর্ট খুলুন, অ্যাডমিন "
            "পুরো প্রসঙ্গ দেখবেন। OTP, পাসওয়ার্ড বা পেমেন্ট PIN কাউকে "
            "দেবেন না — 'সাপোর্ট' দাবি করলেও নয়।"
        ),
    },
    {
        "topic": "market_report",
        "title": "Rental market report",
        "title_bn": "ভাড়ার বাজার রিপোর্ট",
        "keywords": [
            "market report",
            "market trend",
            "area price",
            "rent trend",
            "বাজার রিপোর্ট",
            "বাজার",
            "এলাকার ভাড়া",
            "ট্রেন্ড",
        ],
        "answer": (
            "The platform publishes a weekly rental market report: per-area "
            "average and median rents, demand direction, availability and a "
            "30-day forecast, plus which areas are rising and falling. "
            "Landlords who opt in receive it by email. It's built from "
            "real listing, booking and search data — not opinions."
        ),
        "answer_bn": (
            "প্ল্যাটফর্ম সাপ্তাহিক ভাড়ার বাজার রিপোর্ট প্রকাশ করে: এলাকা "
            "ভেদে গড় ও মধ্যমা ভাড়া, চাহিদার দিক, প্রাপ্যতা আর ৩০ দিনের "
            "ফোরকাস্ট, সাথে কোন এলাকা বাড়ছে বা কমছে। অপ্ট-ইন করা "
            "বাড়িওয়ালারা ইমেইলে পান। আসল লিস্টিং, বুকিং আর সার্চ ডেটা "
            "দিয়ে তৈরি — মতামত নয়।"
        ),
    },
    {
        "topic": "pricing_advice",
        "title": "AI pricing advice",
        "title_bn": "AI মূল্য পরামর্শ",
        "keywords": [
            "price advice",
            "pricing",
            "how much rent",
            "suggested price",
            "recommended price",
            "মূল্য",
            "দাম কত",
            "সাজেস্টেড প্রাইস",
        ],
        "answer": (
            "Landlords get an AI price recommendation on each listing: the "
            "area's median rent, similar listings, demand trend and a "
            "suggested price range. The landlord always decides — the "
            "suggestion is a starting point, never an automatic change."
        ),
        "answer_bn": (
            "বাড়িওয়ালারা প্রতিটি লিস্টিংয়ে AI মূল্য পরামর্শ পান: এলাকার "
            "মধ্যমা ভাড়া, অনুরূপ লিস্টিং, চাহিদার প্রবণতা আর সাজেস্টেড "
            "প্রাইস রেঞ্জ। সিদ্ধান্ত সবসময় বাড়িওয়ালার — পরামর্শ শুধু "
            "শুরু করার জায়গা, কখনো অটোমেটিক পরিবর্তন নয়।"
        ),
    },
    {
        "topic": "map_search",
        "title": "Search & map",
        "title_bn": "সার্চ ও ম্যাপ",
        "keywords": [
            "search",
            "map",
            "filter",
            "area",
            "find room",
            "nearby",
            "সার্চ",
            "ম্যাপ",
            "ফিল্টার",
            "রুম খুঁজব",
        ],
        "answer": (
            "Search by area, budget, room type, gender preference, "
            "verified-only and more; the map shows listings with commute "
            "times and neighborhood intel. The Copilot (AI assistant) can "
            "also find rooms conversationally in Bangla or English — try "
            '"বসুন্ধরায় ১৫ হাজারের মধ্যে একটা রুম".'
        ),
        "answer_bn": (
            "এলাকা, বাজেট, রুমের ধরন, জেন্ডার প্রেফারেন্স, শুধু ভেরিফায়েড "
            "ইত্যাদি দিয়ে সার্চ করুন; ম্যাপে যাতায়াতের সময় আর এলাকার "
            "তথ্যসহ লিস্টিং দেখায়। Copilot (AI সহকারী) দিয়েও বাংলা বা "
            'ইংরেজিতে রুম খুঁজতে পারেন — চেষ্টা করুন "বসুন্ধরায় ১৫ হাজারের '
            'মধ্যে একটা রুম"।'
        ),
    },
]

# Fallback doc — shown when nothing in the corpus matches.
FALLBACK: dict = {
    "topic": "general",
    "title": "How can I help?",
    "title_bn": "কীভাবে সাহায্য করতে পারি?",
    "answer": (
        "I couldn't match that to a help article yet. I can answer questions "
        "about listing rooms, promotion tiers, bookings, security deposits, "
        "payments, refunds, NID verification, chat safety, reporting and "
        "blocking, fraud protection, saved searches, referrals, disputes and "
        "the rental agreement. Try asking in simpler words in Bangla or "
        "English — or use the report/dispute flow for account-specific "
        "issues."
    ),
    "answer_bn": (
        "আপনার প্রশ্নটি এখনো কোনো হেল্প আর্টিকেলে মেলাতে পারিনি। আমি "
        "উত্তর দিতে পারি: রুম লিস্টিং, প্রমোশন টিয়ার, বুকিং, সিকিউরিটি "
        "ডিপোজিট, পেমেন্ট, রিফান্ড, NID ভেরিফিকেশন, চ্যাট নিরাপত্তা, "
        "রিপোর্ট ও ব্লক, ফ্রড সুরক্ষা, সেভড সার্চ, রেফারেল, ডিসপিউট আর "
        "ভাড়ার চুক্তি নিয়ে। সহজ ভাষায় বাংলা বা ইংরেজিতে আবার জিজ্ঞেস "
        "করুন — অথবা অ্যাকাউন্ট সংক্রান্ত সমস্যায় রিপোর্ট/ডিসপিউট ফ্লো "
        "ব্যবহার করুন।"
    ),
}


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower(), re.UNICODE)


def _render(doc: dict) -> dict:
    """Render a doc (injecting live platform facts for dynamic docs) and
    return the API shape."""
    answer, answer_bn = doc["answer"], doc["answer_bn"]
    if doc.get("dynamic"):
        tiers = settings.LISTING_TIER_PRICING
        tier_prices = ", ".join(
            f"{tier.capitalize()} ৳{int(price):,}" for tier, price in tiers.items() if price
        )
        facts = {
            "tier_days": settings.LISTING_TIER_DURATION_DAYS,
            "tier_prices": tier_prices,
        }
        try:
            answer = answer.format(**facts)
            answer_bn = answer_bn.format(**facts)
        except (KeyError, ValueError):
            pass
    return {
        "topic": doc["topic"],
        "title": doc["title"],
        "title_bn": doc["title_bn"],
        "answer": answer,
        "answer_bn": answer_bn,
        "grounded": True,
    }


def support_answer(message: str) -> dict:
    """Answer a support question from the corpus. Deterministic retrieval:
    keyword-overlap scoring (substring match, case-insensitive, bilingual);
    highest score wins, ties resolved by corpus order. No match → the
    transparent fallback with ``grounded: false``."""
    message_lower = message.lower()

    best: tuple[int, dict] = (0, {})
    for doc in SUPPORT_DOCS:
        score = sum(1 for keyword in doc["keywords"] if keyword in message_lower)
        if score > best[0]:
            best = (score, doc)

    if best[0] == 0:
        fallback = dict(FALLBACK)
        fallback["grounded"] = False
        return fallback

    result = _render(best[1])
    result["matched_keywords"] = [kw for kw in best[1]["keywords"] if kw in message_lower][:5]
    return result
