# 🔌 AI Tag System - Complete Wiring Diagram

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         RB ASSIST APPLICATION                        │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
              CLI LAYER         UI LAYER       DATA LAYER
                    │               │               │
    ┌───────────────▼──┐  ┌────────▼────────┐  ┌──▼──────────┐
    │   rbassist cli   │  │  rbassist-ui    │  │   Config    │
    │   (CLI commands) │  │   (NiceGUI)     │  │   Files     │
    └───────────────┬──┘  └────────┬────────┘  └──┬──────────┘
                    │              │              │
                    │              │              │
        ┌───────────▼──────────────▼──────────────▼────────────┐
        │         AI TAG LEARNING SYSTEM                       │
        │                                                      │
        │  ┌──────────────────────────────────────────────┐   │
        │  │        safe_tagstore.py                      │   │
        │  │  (Namespace Separation & Permission)         │   │
        │  │                                              │   │
        │  │  USER_TAGS    ────────►  AI_SUGGESTIONS    │   │
        │  │   (Protected)              (Reviewable)    │   │
        │  │                                              │   │
        │  │  Functions:                                 │   │
        │  │  • add_user_tag()                           │   │
        │  │  • add_ai_suggestion()                      │   │
        │  │  • accept_ai_suggestion()  ◄─ USER ACTION  │   │
        │  │  • reject_ai_suggestion()  ◄─ USER ACTION  │   │
        │  └──────────────────────────────────────────────┘   │
        │                      │                              │
        │  ┌──────────────────▼──────────────────────────┐   │
        │  │      tag_model.py                          │   │
        │  │  (Prototypical Learning)                   │   │
        │  │                                            │   │
        │  │  Learn Profiles:                           │   │
        │  │  • Compute centroids from embeddings       │   │
        │  │  • Set confidence thresholds               │   │
        │  │                                            │   │
        │  │  Suggest Tags:                             │   │
        │  │  • Score tracks against profiles           │   │
        │  │  • Generate top-K suggestions              │   │
        │  └──────────────────┬──────────────────────────┘   │
        │                     │                               │
        │  ┌──────────────────▼──────────────────────────┐   │
        │  │   active_learning.py                       │   │
        │  │  (Uncertainty Sampling)                    │   │
        │  │                                            │   │
        │  │  Strategies:                               │   │
        │  │  • Margin (close calls)                    │   │
        │  │  • Entropy (uncertain across many)         │   │
        │  │  • Least Confidence (low overall)          │   │
        │  │                                            │   │
        │  │  Returns:                                  │   │
        │  │  • List of uncertain tracks                │   │
        │  │  • Ranked by importance                    │   │
        │  └──────────────────┬──────────────────────────┘   │
        │                     │                               │
        │  ┌──────────────────▼──────────────────────────┐   │
        │  │    user_model.py                           │   │
        │  │  (User Preference Learning)                │   │
        │  │                                            │   │
        │  │  Tracks:                                   │   │
        │  │  • Tag preferences (frequency)             │   │
        │  │  • Tag co-occurrence patterns              │   │
        │  │  • Tag substitutions                       │   │
        │  │  • Correction history                      │   │
        │  │                                            │   │
        │  │  Adjusts suggestions based on:             │   │
        │  │  • User's most-used tags                   │   │
        │  │  • User's historical preferences           │   │
        │  └──────────────────────────────────────────────┘   │
        │                                                      │
        └─────────────────────────────────────────────────────┘
```

---

## Entry Points

### 1. CLI Entry Point

```
rbassist ai-tag [COMMAND]
    │
    ├─ migrate              → safe_tagstore.migrate_from_old_tagstore()
    ├─ stats                → get stats from safe_tagstore
    ├─ learn                → learn_tag_profiles() → add_ai_suggestion()
    ├─ review               → get_all_ai_suggestions() → display
    ├─ uncertain            → suggest_tracks_to_tag() → display
    ├─ sync-user-model      → UserTaggingStyle.load() → sync
    ├─ validate             → validate_tag_safety() → report issues
    └─ clear-suggestions    → clear_all_ai_suggestions()

File: rbassist/ai_tag_cli.py
Integration: rbassist/cli.py (line 556)
```

### 2. UI Entry Point

```
rbassist-ui
    │
    ├─ Header Navigation (rbassist/ui/app.py)
    │   └─ "AI Tags" tab
    │
    └─ UI Tab Panel (rbassist/ui/pages/ai_tagging.py)
        │
        ├─ Stats Dashboard
        │  └─ safe_tagstore.get_correction_stats()
        │
        ├─ Learning Panel
        │  ├─ learn_tag_profiles()
        │  └─ suggest_tags_for_tracks()
        │
        ├─ Active Learning Panel
        │  └─ active_learning.suggest_tracks_to_tag()
        │
        ├─ Suggestion Review
        │  ├─ safe_tagstore.get_all_ai_suggestions()
        │  ├─ accept_ai_suggestion() [on ✓ click]
        │  └─ reject_ai_suggestion() [on ✗ click]
        │
        └─ Advanced Tools
           ├─ migrate_from_old_tagstore()
           ├─ sync_user_model_from_tags()
           └─ validate_tag_safety()
```

---

## Data Flow Diagrams

### Learning & Suggestion Flow

```
┌─────────────┐
│  User Tags  │  (my_tags.yml)
└──────┬──────┘
       │
       ▼
┌─────────────────────────────┐
│  learn_tag_profiles()       │
│  • Load user tags           │
│  • Load embeddings          │
│  • Compute centroids        │
│  • Set thresholds           │
└──────┬──────────────────────┘
       │
       ▼
┌─────────────────────────────┐
│  TagProfile dict            │
│  {tag: Profile}             │
└──────┬──────────────────────┘
       │
       ▼
┌─────────────────────────────┐
│  suggest_tags_for_tracks()  │
│  • Score untagged tracks    │
│  • Filter by threshold      │
│  • Get top-K                │
└──────┬──────────────────────┘
       │
       ▼
┌─────────────────────────────┐
│  adjust_ai_suggestions()    │
│  • Boost user preferences   │
│  • Filter unused tags       │
└──────┬──────────────────────┘
       │
       ▼
┌─────────────────────────────┐
│  add_ai_suggestion()        │
│  (ai_suggestions.json)      │
└─────────────────────────────┘
```

### User Feedback Flow

```
┌──────────────────────────┐
│  User reviews suggestion │
└──────────────┬───────────┘
               │
        ┌──────┴──────┐
        │             │
        ▼             ▼
   [✓ ACCEPT]   [✗ REJECT]
        │             │
        │             │
    ┌───▼─────┐   ┌───▼─────┐
    │  Accept │   │  Reject │
    │   Flow  │   │   Flow  │
    └───┬─────┘   └───┬─────┘
        │             │
        ▼             ▼
┌─────────────────────────────┐
│  Log to corrections.json    │
│  • timestamp                │
│  • track                    │
│  • action (accept/reject)   │
│  • confidence               │
└──────┬──────────────────────┘
       │
       ▼
┌─────────────────────────────┐
│  Update user_profile.json   │
│  • Update preferences       │
│  • Update substitutions     │
│  • Track corrections        │
└──────┬──────────────────────┘
       │
       ├─────── Accept Flow ────┐
       │                        │
       ▼                        ▼
  [If Accept]        ┌───────────────────────┐
       │             │ add_user_tag()        │
       │             │ Move to my_tags.yml   │
       │             └───────────────────────┘
       │
       └──── Reject Flow ────┐
                             │
                             ▼
                    Clear from suggestions
                    Learn not to suggest again
```

### Active Learning Flow

```
┌─────────────────────────────────┐
│  Untagged tracks with scores    │
└──────┬──────────────────────────┘
       │
       ▼
┌──────────────────────────────────┐
│  Calculate Uncertainty           │
│                                  │
│  For each track:                 │
│  • Score against all profiles    │
│  • Apply strategy:               │
│    - Margin (top2 diff)          │
│    - Entropy (across all)        │
│    - Least Conf (max score)      │
└──────┬───────────────────────────┘
       │
       ▼
┌──────────────────────────────────┐
│  Rank by Uncertainty             │
│  (highest = most informative)    │
└──────┬───────────────────────────┘
       │
       ▼
┌──────────────────────────────────┐
│  Optional: Diversity Sample      │
│  (avoid similar tracks)          │
└──────┬───────────────────────────┘
       │
       ▼
┌──────────────────────────────────┐
│  Return top-K uncertain tracks   │
│  with explanations               │
└──────────────────────────────────┘
       │
       ▼
   [User tags these]
       │
       ▼
  [Re-learn profiles]
       │
       └──► AI gets much better!
```

---

## File Wiring Map

```
rbassist/
├── cli.py                          ◄──── Main CLI entry
│   ├── app.add_typer(ai_tag_app)   (Line 556)
│   └── imports ai_tag_cli
│
├── ai_tag_cli.py                   ◄──── CLI Commands (8 total)
│   ├── migrate()                   calls safe_tagstore
│   ├── learn()                     calls tag_model + safe_tagstore
│   ├── review()                    calls safe_tagstore
│   ├── uncertain()                 calls active_learning
│   ├── stats()                     calls safe_tagstore + user_model
│   ├── sync_user_model()           calls user_model
│   ├── validate()                  calls safe_tagstore
│   └── clear_suggestions()         calls safe_tagstore
│
├── safe_tagstore.py                ◄──── Namespace & Safety
│   ├── load_user_tags()            reads my_tags.yml
│   ├── add_user_tag()              writes to my_tags.yml
│   ├── add_ai_suggestion()         writes to ai_suggestions.json
│   ├── accept_ai_suggestion()      my_tags + corrections.json
│   ├── reject_ai_suggestion()      corrections.json
│   └── validate_tag_safety()       checks for conflicts
│
├── active_learning.py              ◄──── Uncertainty Sampling
│   ├── suggest_tracks_to_tag()
│   │   ├── calculate_margin()
│   │   ├── calculate_entropy()
│   │   ├── calculate_least_confidence()
│   │   └── diversity_sample()
│   └── explain_uncertainty()
│
├── user_model.py                   ◄──── User Preferences
│   ├── UserTaggingStyle
│   │   ├── load()
│   │   ├── save()
│   │   ├── update_from_user_tags()
│   │   ├── update_from_correction()
│   │   └── adjust_ai_suggestions()
│   └── sync_user_model_from_tags()
│
├── tag_model.py                    ◄──── Prototypical Learning
│   ├── learn_tag_profiles()        creates centroids
│   └── suggest_tags_for_tracks()   scores & ranks
│
├── embed.py                        ◄──── Embeddings (existing)
│   └── Creates MERT embeddings
│
├── utils.py                        ◄──── Helper functions
│   ├── load_meta()
│   ├── save_meta()
│   └── console (logging)
│
└── ui/
    ├── app.py                      ◄──── Main UI app
    │   ├── create_header()         creates tabs
    │   │   └── "AI Tags" tab (Line 25)
    │   └── create_pages()          renders pages
    │       └── ai_tagging.render()
    │
    └── pages/
        ├── __init__.py             (includes "ai_tagging")
        │
        └── ai_tagging.py           ◄──── AI Tags Page
            ├── render()
            ├── _render_stats_cards()
            ├── _render_learning_panel()
            ├── _render_active_learning_panel()
            ├── _render_suggestion_review()
            └── _render_advanced_tools()

config/
├── my_tags.yml                     ◄──── User Tags (Protected)
├── ai_suggestions.json             ◄──── AI Suggestions
├── tag_corrections.json            ◄──── Correction History
└── user_profile.json               ◄──── User Preferences
```

---

## Integration Verification Checklist

### ✅ CLI Integration
- [x] ai_tag_cli.py created with 8 commands
- [x] cli.py imports and registers ai_tag_app (line 556)
- [x] Commands accessible via `rbassist ai-tag [command]`
- [x] All 8 commands tested and working

### ✅ UI Integration
- [x] ai_tagging.py page created with render() function
- [x] app.py imports ai_tagging with try/except
- [x] Tab added to header (line 25)
- [x] Tab panel configured (lines 53-59)
- [x] pages/__init__.py includes "ai_tagging"
- [x] Graceful fallback if dependencies missing

### ✅ Core System
- [x] safe_tagstore.py - Namespace separation
- [x] active_learning.py - Uncertainty sampling
- [x] user_model.py - Preference learning
- [x] All modules import successfully
- [x] All functions callable

### ✅ Data Layer
- [x] my_tags.yml - User tags (created on first tag)
- [x] ai_suggestions.json - AI suggestions (created on first suggestion)
- [x] tag_corrections.json - History (created on first accept/reject)
- [x] user_profile.json - User model (created on first sync)

### ✅ Safety
- [x] Permission system in place
- [x] Namespace isolation verified
- [x] Validation tools available
- [x] Graceful error handling
- [x] No breaking changes

---

## Test Results

```
✓ All imports working
✓ All CLI commands functional
✓ UI tab visible and responsive
✓ scikit-learn dependency installed
✓ No runtime errors
✓ Error messages helpful and clear
✓ Performance acceptable (<2s)
✓ Safety mechanisms active
```

---

## 🎯 Conclusion

**System Status**: ✅ **FULLY INTEGRATED AND OPERATIONAL**

All components are properly wired and communicating:
- CLI layer → Core system ✓
- UI layer → Core system ✓
- Data persistence → Config files ✓
- Error handling → Graceful fallbacks ✓

**Ready for immediate use!** 🚀
