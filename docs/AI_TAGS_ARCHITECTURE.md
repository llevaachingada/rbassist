# AI Tag Learning System Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    RB Assist AI Tag Learning                 │
└─────────────────────────────────────────────────────────────┘

┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│   User Tags  │       │AI Suggestions│       │User Feedback │
│ (my_tags.yml)│       │ (.json)      │       │ (.json)      │
└──────┬───────┘       └──────┬───────┘       └──────┬───────┘
       │                      │                       │
       └──────────────────────┼───────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │   Safe Tagstore    │
                    │ (Namespace Safety) │
                    └─────────┬──────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
       ┌──────▼─────┐  ┌──────▼──────┐  ┌────▼─────┐
       │Tag Learning│  │  Active     │  │   User   │
       │  (Profiles)│  │  Learning   │  │  Model   │
       └──────┬─────┘  └──────┬──────┘  └────┬─────┘
              │               │               │
              └───────────────┼───────────────┘
                              │
                    ┌─────────▼──────────┐
                    │   MERT Embeddings  │
                    │ (1024-dim vectors) │
                    └────────────────────┘
```

## Component Details

### 1. Safe Tagstore ([safe_tagstore.py](../rbassist/safe_tagstore.py))

**Purpose**: Namespace separation and permission management

**Key Features**:
- USER namespace: Manual tags (protected)
- AI namespace: Suggestions (reviewable)
- Permission checks prevent AI from modifying user tags
- Correction history tracking

**Key Functions**:
```python
# User namespace (protected)
add_user_tag(track, tag)
remove_user_tag(track, tag)
get_user_tags(track)

# AI namespace (separate)
add_ai_suggestion(track, tag, confidence)
get_ai_suggestions(track, min_confidence)
clear_ai_suggestions(track)

# User actions (only way AI → User)
accept_ai_suggestion(track, tag)
reject_ai_suggestion(track, tag, reason)
```

**Storage**:
```yaml
# config/my_tags.yml (USER TAGS)
version: "1.0"
last_modified: "2024-01-15T10:30:00Z"
tracks:
  "/path/to/track1.mp3": ["Peak Hour", "Techno"]
  "/path/to/track2.mp3": ["Warm-up"]
```

```json
// config/ai_suggestions.json (AI SUGGESTIONS)
{
  "version": "1.0",
  "generated": "2024-01-15T11:00:00Z",
  "suggestions": {
    "/path/to/track3.mp3": {
      "Peak Hour": 0.85,
      "Techno": 0.72
    }
  }
}
```

### 2. Tag Model ([tag_model.py](../rbassist/tag_model.py))

**Purpose**: Prototypical learning from few examples

**Algorithm**:
```
For each tag T:
  1. Collect embeddings E = {e1, e2, ..., en} of tracks with tag T
  2. Compute centroid: c = mean(E)
  3. Compute similarities: s_i = e_i · c (dot product)
  4. Compute threshold: θ = mean(s) - std(s)
  5. Profile = (c, θ, mean(s), std(s), n)

For untagged track with embedding e:
  1. Score against each profile: score_T = e · c_T
  2. If score_T >= θ_T: suggest tag T with confidence=score_T
```

**Key Data Structure**:
```python
@dataclass
class TagProfile:
    tag: str              # Tag name
    centroid: np.ndarray  # Mean embedding (1024-dim)
    threshold: float      # Acceptance threshold
    mean_sim: float       # Mean similarity to centroid
    std_sim: float        # Std deviation of similarities
    samples: int          # Number of training examples
```

**Research Basis**: Prototypical Networks (Snell et al., 2017)

### 3. Active Learning ([active_learning.py](../rbassist/active_learning.py))

**Purpose**: Find most informative tracks to tag

**Strategies**:

#### Margin Sampling (Best)
```python
scores = [score_tag1, score_tag2, ..., score_tagN]
sorted_scores = sort(scores, descending=True)
margin = sorted_scores[0] - sorted_scores[1]
uncertainty = 1.0 - margin
```
**Interpretation**: Low margin = close call between top 2 tags

#### Entropy-Based
```python
probs = softmax(scores)
entropy = -sum(p * log(p) for p in probs)
uncertainty = entropy
```
**Interpretation**: High entropy = uncertain across many tags

#### Least Confidence
```python
uncertainty = 1.0 - max(scores)
```
**Interpretation**: Not confident in any tag

**Key Function**:
```python
suggest_tracks_to_tag(
    untagged_embeddings: Dict[str, np.ndarray],
    profiles: Dict[str, TagProfile],
    strategy: str = "margin",
    top_k: int = 10
) -> List[UncertainTrack]
```

**Research Basis**: Active Learning (Settles, 2012)

### 4. User Model ([user_model.py](../rbassist/user_model.py))

**Purpose**: Learn user's personal tagging style

**Tracks**:
1. **Tag preferences**: Which tags user uses most
2. **Tag co-occurrence**: Which tags appear together
3. **Tag substitutions**: When user corrects AI, what they choose
4. **Correction history**: Full log of accept/reject decisions

**Key Operations**:
```python
# Learn from user behavior
update_from_user_tags(track, tags)
update_from_correction(track, ai_tag, user_tag)

# Predict user preferences
predict_preference(tag_a, tag_b) -> preferred_tag
get_complementary_tags(existing_tags) -> [suggested_tags]
adjust_ai_suggestions(suggestions) -> adjusted_suggestions
```

**Adjustment Logic**:
```python
def adjust_ai_suggestions(suggestions):
    adjusted = {}
    for tag, confidence in suggestions.items():
        # Check substitution pattern
        if user_prefers(other_tag over tag):
            adjusted[other_tag] = confidence * 1.2
        else:
            # Boost frequently used tags
            boost = min(0.1, usage_count(tag) * 0.01)
            adjusted[tag] = confidence + boost
    return adjusted
```

**Research Basis**: Personalized Music Organization (CHI 2024)

### 5. MERT Embeddings ([embed.py](../rbassist/embed.py))

**Model**: m-a-p/MERT-v1-330M (Multi-task Music Understanding)

**What it captures**:
- Timbre (instrument sounds, texture)
- Rhythm (beat patterns, groove)
- Harmony (chord progressions, tonality)
- Energy (intensity, dynamics)

**Output**: 1024-dimensional vector per track

**Why MERT**:
- Pre-trained on large music dataset
- Multi-task: trained for multiple music understanding tasks
- State-of-art for music similarity
- Transfer learning: no need to train from scratch

**Research**: "MERT: Multi-task Music Understanding" (2023)

## Data Flow

### Learning Flow

```
1. User tags tracks manually
   └─> my_tags.yml updated

2. User clicks "Learn & Generate"
   └─> learn_tag_profiles()
       ├─> Load user tags from my_tags.yml
       ├─> Load embeddings from data/embeddings/
       ├─> For each tag: compute centroid profile
       └─> Return {tag: TagProfile}

3. suggest_tags_for_tracks()
   ├─> For each untagged track:
   │   ├─> Score against all profiles
   │   ├─> Filter by threshold
   │   └─> Top-K tags
   ├─> Load user model
   ├─> Adjust suggestions based on user preferences
   └─> add_ai_suggestion() for each

4. AI suggestions saved
   └─> ai_suggestions.json updated
```

### Review Flow

```
1. User views suggestions in UI

2. User clicks ✓ (Accept)
   └─> accept_ai_suggestion()
       ├─> Log acceptance to corrections.json
       ├─> Move tag to my_tags.yml
       ├─> Remove from ai_suggestions.json
       └─> Update user model

3. User clicks ✗ (Reject)
   └─> reject_ai_suggestion()
       ├─> Log rejection to corrections.json
       ├─> Remove from ai_suggestions.json
       └─> Update user model (learn from mistake)
```

### Active Learning Flow

```
1. User clicks "Find Uncertain Tracks"

2. suggest_tracks_to_tag()
   ├─> For each untagged track:
   │   ├─> Score against all profiles
   │   ├─> Calculate uncertainty (margin/entropy/least_conf)
   │   └─> Rank by uncertainty
   └─> Return top-K most uncertain

3. UI displays uncertain tracks with explanations

4. User manually tags these tracks
   └─> High impact: improves AI on most confusing cases
```

## Safety Guarantees

### Namespace Isolation

```python
# ✓ SAFE: User adds tag
add_user_tag(track, tag, source=USER_MANUAL)

# ✓ SAFE: AI adds suggestion (separate namespace)
add_ai_suggestion(track, tag, confidence)

# ✗ BLOCKED: AI cannot directly modify user tags
add_user_tag(track, tag, source=AI_SUGGESTED)  # Raises TagPermissionError!

# ✓ SAFE: Only user can accept (AI → User transition)
accept_ai_suggestion(track, tag)  # Explicit user action required
```

### Validation

```python
validate_tag_safety() -> List[str]:
    issues = []

    # Check 1: No overlap between namespaces
    for track in ai_suggestions:
        if track in user_tags:
            overlap = ai_suggestions[track] ∩ user_tags[track]
            if overlap:
                issues.append(f"Overlap detected: {overlap}")

    # Check 2: Files are readable
    for file in [my_tags.yml, ai_suggestions.json]:
        try:
            read(file)
        except:
            issues.append(f"Corrupted: {file}")

    return issues
```

## Performance Characteristics

### Computational Complexity

```
Learning profiles:
- Time: O(n * d) where n = tracks, d = embedding_dim (1024)
- Space: O(t * d) where t = number of tags
- Typical: ~100ms for 1000 tracks, 50 tags

Generating suggestions:
- Time: O(u * t * d) where u = untagged tracks, t = tags
- Typical: ~1s for 500 untagged tracks, 50 tags

Active learning:
- Time: O(u * t * d) same as suggestions
- Diversity sampling: +O(k^2 * d) where k = top_k
```

### Storage

```
Per track:
- Embedding: 4KB (1024 floats * 4 bytes)
- Metadata: ~1KB

Per tag:
- Profile: 4KB (centroid) + metadata
- User preferences: ~100 bytes

Total for 10,000 tracks, 100 tags:
- Embeddings: 40MB
- Profiles: 400KB
- User data: 10KB
```

## Extension Points

### Adding New Uncertainty Strategies

```python
# In active_learning.py

def calculate_my_strategy(scores: List[float]) -> float:
    """
    Your custom uncertainty metric.
    Higher value = more uncertain.
    """
    # Your logic here
    return uncertainty_score

# Register in suggest_tracks_to_tag():
elif strategy == "my_strategy":
    uncertainty = calculate_my_strategy(scores_list)
    reason = "My custom reason"
```

### Adding User Preference Features

```python
# In user_model.py

class UserTaggingStyle:
    def my_custom_adjustment(self, suggestions):
        """
        Custom logic for adjusting AI suggestions.
        """
        # Your logic here
        return adjusted_suggestions
```

### Custom Profile Types

```python
# In tag_model.py

@dataclass
class MyCustomProfile(TagProfile):
    custom_field: float

    def score(self, vec: np.ndarray) -> float:
        # Custom scoring logic
        return custom_score
```

## Testing

```bash
# Test safe tagstore
python -m pytest tests/test_safe_tagstore.py

# Test tag learning
python -m pytest tests/test_tag_model.py

# Test active learning
python -m pytest tests/test_active_learning.py

# Integration test
python -m pytest tests/test_ai_tag_integration.py
```

## Monitoring

```bash
# Check system health
rbassist ai-tag validate

# See performance stats
rbassist ai-tag stats

# View user model accuracy
rbassist ai-tag sync-user-model
```

## Future Enhancements

### Planned
- [ ] Tag hierarchy support (parent/child tags)
- [ ] Multi-label learning (tag dependencies)
- [ ] Transfer learning between users
- [ ] Confidence calibration (better probability estimates)

### Research Opportunities
- [ ] Graph Neural Networks for tag relationships
- [ ] Fine-tuning MERT on user's library
- [ ] Temporal modeling (how tags change over time)
- [ ] Multi-modal (audio + text descriptions)

## References

1. Snell et al. (2017) - Prototypical Networks for Few-shot Learning
2. Settles (2012) - Active Learning Literature Survey
3. CHI (2024) - Personalized Music Organization
4. MERT (2023) - Multi-task Music Understanding Transformer

## License

See main LICENSE file.
