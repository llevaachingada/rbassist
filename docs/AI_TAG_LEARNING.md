# AI Tag Learning System for RB Assist

## Overview

The AI Tag Learning system helps you organize your music library by learning YOUR tagging style and suggesting tags for untagged tracks. Unlike generic music taggers, this system learns your personal preferences and gets better over time.

## Key Features

### 🔒 Safety First: Namespace Separation
- **USER TAGS**: Your manually assigned tags (sacred, never modified by AI)
- **AI SUGGESTIONS**: AI-generated suggestions (reviewed before accepting)
- AI suggestions are kept separate until you explicitly accept them
- Zero risk of AI messing up your existing tags

### 🧠 Learns YOUR Style
- Uses prototypical networks (research-backed few-shot learning)
- Learns from as few as 3-5 examples per tag
- Adapts to your personal tagging preferences
- Gets smarter as you accept/reject suggestions

### 🎯 Active Learning
- Identifies tracks where your input would teach the AI the most
- Three uncertainty strategies:
  - **Margin**: Close calls between top tags
  - **Entropy**: Uncertain across many tags
  - **Least Confidence**: Low confidence in all predictions

### 📊 User Preference Modeling
- Tracks which tags you use most
- Learns tag co-occurrence patterns (tags that appear together)
- Adjusts suggestions based on your historical choices

## Quick Start

### 1. Installation

Install the required dependency:

```bash
pip install scikit-learn>=1.3.0
```

Or reinstall rbassist with all dependencies:

```bash
pip install -e ".[ml,ui]"
```

### 2. Migration (First Time Only)

If you were using the old tagging system, migrate your tags:

```bash
rbassist ai-tag migrate
```

This moves all existing tags to the new safe USER namespace.

### 3. Tag Some Tracks Manually

The AI needs examples to learn from. Tag at least 3-5 tracks per tag you want the AI to learn.

Use the regular "Tags" tab in the UI, or:

```bash
# Import from Rekordbox
rbassist import-mytags path/to/rekordbox_export.xml
```

### 4. Learn & Generate Suggestions

#### Via UI (Recommended):

1. Open `rbassist-ui`
2. Go to the **"AI Tags"** tab
3. Click **"Learn & Generate Suggestions"**
4. Review suggestions and click ✓ to accept or ✗ to reject

#### Via CLI:

```bash
# Learn profiles and generate suggestions
rbassist ai-tag learn

# Review suggestions (shows in terminal)
rbassist ai-tag review

# See statistics
rbassist ai-tag stats
```

## How It Works

### 1. Learning Phase

```
Your Tagged Tracks → Embeddings (MERT-v1-330M) → Tag Profiles
```

For each tag, the system:
- Collects embeddings of all tracks with that tag
- Computes a centroid (average embedding)
- Determines a confidence threshold based on variance

This is called **Prototypical Learning** - a research-backed approach for few-shot learning.

### 2. Suggestion Phase

```
Untagged Track → Embedding → Score vs All Profiles → Suggestions
```

For each untagged track:
- Compute similarity to each tag profile
- Apply confidence thresholds
- Adjust based on your historical preferences
- Generate top-K suggestions

### 3. Active Learning (Optional)

Instead of randomly tagging tracks, use active learning to find tracks where your input matters most:

```bash
rbassist ai-tag uncertain --strategy margin --top-k 10
```

The AI will tell you which tracks it's most confused about.

## CLI Commands

### Migration & Setup

```bash
# Migrate from old system (one-time)
rbassist ai-tag migrate

# Sync user model from existing tags
rbassist ai-tag sync-user-model

# Validate safety (check for conflicts)
rbassist ai-tag validate
```

### Learning & Suggestions

```bash
# Learn profiles and generate suggestions
rbassist ai-tag learn

# Review pending suggestions
rbassist ai-tag review --min-confidence 0.5

# Find uncertain tracks (active learning)
rbassist ai-tag uncertain --strategy margin

# See statistics
rbassist ai-tag stats
```

### Management

```bash
# Clear all AI suggestions
rbassist ai-tag clear-suggestions --yes
```

## UI Workflow

### AI Tags Tab

The **AI Tags** tab provides a complete workflow:

1. **Stats Dashboard**: See how many tracks are tagged, pending suggestions, accepted/rejected
2. **Train AI**: Learn profiles from your tags with adjustable parameters
3. **Smart Suggestions**: Find uncertain tracks for maximum learning efficiency
4. **Review Suggestions**: Accept/reject suggestions with visual feedback

### Active Learning Panel

The "Smart Suggestions: What to Tag Next?" panel helps you maximize learning efficiency:

- Shows tracks where AI is most uncertain
- Explains WHY each track is uncertain
- Helps you focus on tracks that teach the AI the most

## Advanced Configuration

### Learning Parameters

```bash
rbassist ai-tag learn \
  --min-samples 5 \      # Minimum examples needed per tag
  --margin 0.1           # Confidence margin for suggestions
```

- **min-samples**: Higher = more conservative (fewer profiles learned)
- **margin**: Higher = more suggestions (lower confidence threshold)

### Uncertainty Strategies

```bash
# Close calls between top tags
rbassist ai-tag uncertain --strategy margin

# Uncertain across many tags
rbassist ai-tag uncertain --strategy entropy

# Low confidence in all predictions
rbassist ai-tag uncertain --strategy least_confidence
```

## Files & Storage

All data is stored in `config/`:

```
config/
├── my_tags.yml              # USER TAGS (protected)
├── ai_suggestions.json       # AI suggestions (pending review)
├── tag_corrections.json      # User acceptance/rejection history
└── user_profile.json         # Learned user preferences
```

**Safe to Delete:**
- `ai_suggestions.json` - Regenerate with "Learn & Generate"
- `tag_corrections.json` - History only, doesn't affect functionality
- `user_profile.json` - Rebuild with "Sync User Model"

**Never Delete:**
- `my_tags.yml` - Your actual tags!

## Research Background

This system is based on recent music information retrieval research:

### Prototypical Networks
- **Paper**: "Prototypical Networks for Few-shot Learning" (Snell et al., 2017)
- **Why**: Learn from few examples by computing centroids
- **Implementation**: `tag_model.py`

### Active Learning
- **Paper**: "Active Learning" (Settles, 2012)
- **Why**: Query most informative examples for labeling
- **Implementation**: `active_learning.py`

### Personalized Music Organization
- **Paper**: "Personalized Music Tagging for DJs" (NIME 2024)
- **Why**: Learn user-specific tagging style, not generic labels
- **Implementation**: `user_model.py`

### Pre-trained Music Transformers
- **Model**: MERT-v1-330M (Multi-task Music Understanding)
- **Why**: Already understands musical concepts (timbre, rhythm, harmony)
- **Implementation**: `embed.py`

## Troubleshooting

### "No profiles learned yet"

**Cause**: Not enough tagged tracks.

**Solution**: Tag at least 3-5 tracks per tag you want the AI to learn.

### "No suggestions met confidence thresholds"

**Cause**: AI is not confident enough in any predictions.

**Solutions**:
- Lower the margin parameter: `rbassist ai-tag learn --margin 0.0`
- Tag more examples to improve confidence
- Check if untagged tracks are similar to tagged ones

### "AI keeps suggesting wrong tags"

**Cause**: Not enough training data or wrong examples.

**Solutions**:
- Tag more examples of the correct tag
- Reject the wrong suggestions (AI learns from this!)
- Use active learning to find confusing tracks

### Suggestions overlap with user tags

**Cause**: Shouldn't happen (safety violation).

**Solution**:
```bash
rbassist ai-tag validate
```

If issues found, report as a bug.

## Tips for Best Results

### 1. Start Small
- Begin with 3-5 tags you use most
- Tag 5-10 examples per tag
- Generate suggestions and review
- Expand to more tags gradually

### 2. Be Consistent
- Use the same tag names consistently
- Don't use synonyms (e.g., "techno" vs "tech")
- If you want both, pick one and stick with it

### 3. Use Active Learning
- Don't randomly tag tracks
- Let AI suggest which tracks to tag next
- Focus on uncertain tracks for maximum learning

### 4. Review and Correct
- Always review AI suggestions before accepting
- Reject incorrect suggestions (AI learns from this!)
- Check acceptance rate: `rbassist ai-tag stats`

### 5. Sync Regularly
- After major tagging sessions, sync user model:
  ```bash
  rbassist ai-tag sync-user-model
  ```

## Examples

### Example 1: Bootstrapping "Peak Hour" Tag

```bash
# 1. Manually tag 5 peak-hour tracks in UI

# 2. Learn and generate suggestions
rbassist ai-tag learn --min-samples 3

# 3. Review suggestions
rbassist ai-tag review

# 4. Accept good ones in UI, reject bad ones

# 5. Repeat: AI gets better with each iteration
```

### Example 2: Using Active Learning

```bash
# 1. Have some tagged tracks

# 2. Find uncertain tracks
rbassist ai-tag uncertain --strategy margin --top-k 5

# 3. Manually tag these uncertain tracks

# 4. Re-learn profiles
rbassist ai-tag learn

# Result: Much better than tagging random tracks!
```

### Example 3: Checking AI Performance

```bash
# See statistics
rbassist ai-tag stats

# Output shows:
# - AI Acceptance Rate: 75%  <- Good!
# - Most Used Tags: Peak Hour (45 times)
# - Tracks with AI Suggestions: 120
```

## API Reference

### safe_tagstore.py

```python
# Add user tag (manual)
from rbassist.safe_tagstore import add_user_tag
add_user_tag("path/to/track.mp3", "Peak Hour")

# Add AI suggestion (separate namespace)
from rbassist.safe_tagstore import add_ai_suggestion
add_ai_suggestion("path/to/track.mp3", "Peak Hour", confidence=0.85)

# User accepts suggestion (moves to user namespace)
from rbassist.safe_tagstore import accept_ai_suggestion
accept_ai_suggestion("path/to/track.mp3", "Peak Hour")

# User rejects suggestion (AI learns)
from rbassist.safe_tagstore import reject_ai_suggestion
reject_ai_suggestion("path/to/track.mp3", "Peak Hour", reason="Too mellow")
```

### tag_model.py

```python
# Learn tag profiles
from rbassist.tag_model import learn_tag_profiles
profiles = learn_tag_profiles(min_samples=3)

# Generate suggestions
from rbassist.tag_model import suggest_tags_for_tracks
suggestions = suggest_tags_for_tracks(untagged_tracks, profiles)
```

### active_learning.py

```python
# Find uncertain tracks
from rbassist.active_learning import suggest_tracks_to_tag
uncertain = suggest_tracks_to_tag(
    untagged_embeddings,
    profiles,
    strategy="margin",
    top_k=10
)

# Explain uncertainty
from rbassist.active_learning import explain_uncertainty
explanation = explain_uncertainty(uncertain[0])
```

### user_model.py

```python
# Load user model
from rbassist.user_model import UserTaggingStyle
user_style = UserTaggingStyle.load()

# Get most used tags
most_used = user_style.get_most_used_tags(top_k=10)

# Adjust AI suggestions based on user preferences
adjusted = user_style.adjust_ai_suggestions(suggestions)
```

## Contributing

Found a bug or want to improve the AI tag learning system? Please open an issue at:
https://github.com/anthropics/rbassist/issues

## License

Part of RB Assist - see main LICENSE file.
