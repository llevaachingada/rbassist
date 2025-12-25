# RBAssist Roadmap & Wishlist

## Signed: Claude (AI Assistant)

### Embedding & Analysis Robustness (HIGH PRIORITY)

#### Embedding Reliability
- [ ] Implement comprehensive error recovery during large library embedding
- [ ] Add detailed logging for failed/skipped track embeddings
- [ ] Create resumable embedding process
- [ ] Support checkpointing for multi-day/interrupted embedding runs

#### Performance Optimizations
- [ ] Optimize memory usage for large libraries (100k+ tracks)
- [ ] Implement intelligent batching strategies
- [ ] Add configurable resource throttling
- [ ] Support distributed/multi-machine embedding

#### Error Handling
- [ ] Graceful handling of:
  * Corrupted audio files
  * Unsupported file formats
  * Insufficient system resources
  * Network/storage interruptions

#### UI/UX
- [ ] Library table virtual scrolling / true pagination for 10k+ tracks (current plan: pagination; future: infinite scroll).
- [ ] Beatgrid waveform preview: refine layout/controls and consider downbeat markers/zoom; current preview shows first ~16 bars on demand.

#### Beatgrid Improvements
- [ ] Swap librosa beat tracker for GPU-optional CRNN/DBN (beat+downbeat) to improve syncopated/non-4x4 material.
- [ ] Optional auto-beatgrid step in `analyze` pipeline (flagged, defaults to fixed) with confidence-based fallback.
- [ ] UI preview of detected segments + confidence with one-click fallback to fixed BPM.

I apologize, but I cannot apply the edit to a previous code without context. Could you provide the previous code that this recommendation engine enhancement is meant to improve?

From the code snippet you've shared, it looks like a robust library embedding function with several key improvements:

1. Resumable embedding process
2. Error handling and tolerance
3. Progress tracking with tqdm
4. Multiple embedding strategies (full track, segmented)
5. Logging and state management

To help me better assist you, could you share:
- The previous code this is meant to replace
- The specific context or problem this enhancement is addressing
- Any additional requirements or context about the recommendation engine

Once I have that information, I can help you understand how to integrate these enhancements effectively.

#### Embedding Quality
- [ ] Multi-model embedding ensemble
- [ ] Advanced timbre and rhythm feature extraction
- [ ] Support for more advanced music embedding models
- [ ] Configurable embedding strategies

#### Recommendation Flexibility
- [ ] More sophisticated similarity metrics
- [ ] Support for user-guided recommendation weighting
- [ ] Contextual recommendation adaptation

### Workflow Improvements

#### Library Management
- [ ] Intelligent track deduplication UI: wire Tools → Duplicate Finder to `duplicates.find_duplicates` and show KEEP/REMOVE pairs with CDJ warnings.
- [ ] Automated metadata cleanup helpers (artist/title normalization, missing BPM/key reports).
- [ ] Advanced tag inference UI: expose `tags-auto` parameters in the Tagging page (min_samples, margin, prune_margin, apply) beyond the current CSV-only GUI flow.
- [ ] Comprehensive library health checks (counts of missing embeddings/BPM/key/cues, corrupt files, inconsistent tags).

#### User Preferences
- [ ] Machine learning-based preference learning
- [ ] Adaptive recommendation refinement
- [ ] User interaction feedback loop

### Technical Debt & Infrastructure

#### Testing & Validation
- [ ] Comprehensive unit and integration tests
- [ ] Performance benchmarking suite
- [ ] Cross-platform compatibility testing

#### Documentation
- [ ] Inline code documentation
- [ ] Detailed developer and user guides
- [ ] Architecture decision records

### Future Exploration

#### Experimental Features
- [ ] DJ-style intelligent playlist generation surfaced in the Discover/Tools pages (front-end for existing `int-pl` logic).
- [ ] Advanced beat grid analysis and visual cue editing tools in the GUI.
- [ ] Automatic set preparation tools (end-to-end: seed → recommendations → ordered export with cues).
- [ ] Cloud/distributed recommendation services (optional, opt-in only; keep local-first workflow primary).

## Contributing

Interested in helping? Check the current roadmap and open issues. 
Pull requests welcome!

---
Last Updated: 2025-12-09
Curator: Claude & Hunter
