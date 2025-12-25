# AI Tags Quick Start Guide

## 🚀 Get Started in 5 Minutes

### Step 1: Install

```bash
pip install scikit-learn>=1.3.0
```

### Step 2: Migrate (First Time Only)

If you have existing tags:

```bash
rbassist ai-tag migrate
```

### Step 3: Tag Some Tracks

Tag at least 5 tracks per tag you want AI to learn.

### Step 4: Generate AI Suggestions

**Option A: UI (Recommended)**
```bash
rbassist-ui
# Go to "AI Tags" tab → Click "Learn & Generate Suggestions"
```

**Option B: CLI**
```bash
rbassist ai-tag learn
```

### Step 5: Review & Accept

In the UI:
- ✓ = Accept suggestion (moves to your tags)
- ✗ = Reject suggestion (AI learns from this)

## 📋 Daily Workflow

### Morning: Generate Suggestions
```bash
rbassist ai-tag learn
```

### Afternoon: Review in UI
```bash
rbassist-ui
# AI Tags tab → Review suggestions
```

### Evening: Tag Uncertain Tracks
```bash
rbassist ai-tag uncertain --top-k 5
# Tag the suggested tracks in UI
```

## 🎯 Key Commands

```bash
# See stats
rbassist ai-tag stats

# Generate suggestions
rbassist ai-tag learn

# Find tracks to tag next
rbassist ai-tag uncertain

# Check AI performance
rbassist ai-tag stats
```

## 💡 Tips

1. **Start small**: 3-5 tags, 5-10 examples each
2. **Use active learning**: Tag uncertain tracks first
3. **Review regularly**: AI improves as you accept/reject
4. **Be consistent**: Use same tag names

## ⚠️ Safety

- AI suggestions are **separate** from your tags
- Nothing changes until you click ✓ to accept
- Your manual tags are **protected**

## 🆘 Common Issues

### "No profiles learned"
→ Tag more tracks (need 3-5 per tag)

### "No suggestions generated"
→ Lower margin: `rbassist ai-tag learn --margin 0.0`

### "Wrong suggestions"
→ Reject them! AI learns from rejections.

## 📚 Full Documentation

See [AI_TAG_LEARNING.md](./AI_TAG_LEARNING.md) for complete docs.
