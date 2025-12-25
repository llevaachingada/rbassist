# Quick Start Guide - New Features

## 🎵 Process Cues for Your Entire Library

### Option 1: Batch Process Everything (5 seconds)
1. Open rbassist UI
2. Go to **Cues** tab
3. Click **"Process music folders"**
4. Wait for progress bar to complete
5. Done! All tracks have cues now

### Option 2: Process Single File
1. Go to **Cues** tab
2. Click **"Browse"** to select a file
3. Click **"Process single file"**
4. Check the status message

### Settings Available:
- **Duration cap (s)**: Limit to first N seconds (0 = full track)
- **Overwrite existing**: Reprocess tracks that already have cues

---

## 🤖 Train AI to Tag Your Tracks

### Step 1: Tag Some Tracks Manually (5-10 minutes)
1. Go to **Tagging** tab
2. Select a track in the table
3. Type in tags: "Techno", "Deep", "Tech House", etc.
4. **Important:** Use consistent tag names! ("Techno" not "Tech")
5. Do this for 5-10 tracks per tag

### Step 2: Train the AI (1 minute)
1. Go to **AI Tags** tab (shows "AI Tag Learning")
2. Click **"Learn & Generate Suggestions"**
3. System learns your tagging style
4. Status shows: "Learned 71 profiles from user tags"

### Step 3: Review AI Suggestions (5-10 minutes)
1. Still in **AI Tags** tab
2. Scroll down to **"Review AI Suggestions"** section
3. For each suggestion, click:
   - ✓ (checkmark) to accept
   - ✗ (X) to reject
4. AI learns from your decisions!

### Step 4: Improve (Repeat Steps 1-3)
1. Tag a few more tracks
2. Click "Learn & Generate Suggestions" again
3. Notice AI gets better over time!

---

## 💡 Smart Tagging (Find What to Tag Next)

1. Go to **AI Tags** tab
2. Look for **"Smart Suggestions: What to Tag Next?"** section
3. Click **"Find Uncertain Tracks"**
4. AI shows you which tracks would teach it the most
5. Tag those first for fastest improvement

---

## ⚡ Pro Tips

### For Best Results:
- **Be consistent** with tag names (use "Techno" every time, not "Tech")
- **Tag 5-10 examples** per tag before training
- **Start with 3-5 tags** you use most, expand gradually
- **Review suggestions carefully** - feedback trains the AI
- **Tag uncertain tracks first** - they teach AI the fastest

### What Tags Should You Use?
Use tags that matter to you:
- Genre: Techno, House, Deep House, Minimal, etc.
- Vibe: Dark, Groovy, Energetic, Uplifting, etc.
- Use Case: Club, Radio, Workout, Chill, etc.
- Custom: Whatever helps you find tracks

### How Often to Retrain?
After tagging 5-10 new tracks:
1. Click "Learn & Generate Suggestions"
2. Review and accept/reject suggestions
3. Rinse and repeat!

---

## ❓ FAQ

**Q: How many tagged tracks do I need?**
A: Minimum 3-5 per tag. More = better accuracy. Start small, expand.

**Q: Can AI modify my original tags?**
A: NO! User tags are protected. Only AI suggestions appear separately.

**Q: What if AI suggests wrong tags?**
A: Click ✗ to reject. AI learns from your feedback!

**Q: Can I undo a suggestion accept?**
A: Go to Tagging tab and manually remove the tag.

**Q: How long does training take?**
A: 30 seconds for 50 tags, 2 seconds to generate suggestions.

**Q: Will my tags be uploaded anywhere?**
A: NO! Everything stays local on your computer.

**Q: Can I change accepted AI suggestions?**
A: Yes! They're stored like regular tags. Edit anytime.

**Q: What's the difference between the three strategies?**
A: (margin, entropy, least_confidence) - they find uncertain tracks differently. Try all three!

---

## 🔧 System Status

Currently working:
- ✅ Cues batch processing (new!)
- ✅ AI tag learning (fully tested!)
- ✅ Beatgrid analysis (fixed & improved!)
- ✅ Duplicate finder (basic scan)
- ✅ Export to Rekordbox

Not yet available:
- ⏳ Intelligent playlist builder
- ⏳ Library pagination (loads all tracks)
- ⏳ Non-4/4 time signatures

---

## 📊 Your Library Status

Check the Library tab for statistics:
- **Total tracks**: ~13,400
- **Embedded**: ~3,000
- **Analyzed** (BPM/Key): ~11,800
- **Tagged**: ~2,600 (you can train with these!)
- **With Cues**: 0 (will be 13,400 after batch processing!)

---

## 🚀 Get Started Now!

### 5-Minute Setup:
1. Cues Tab → Click "Process music folders" → Go get coffee ☕
2. Tagging Tab → Tag 5 tracks with your favorite tags
3. AI Tags Tab → Click "Learn & Generate Suggestions"
4. Review the suggestions and click ✓ or ✗

You now have:
- Cues for every track
- AI learning your tagging style
- Smart suggestions appearing automatically

**That's it! You're ready to go!** 🎉

---

## 📞 Need Help?

- Check error messages - they're usually very specific
- Run tests: `python test_ai_tagging.py` or `python test_beatgrid.py`
- Read detailed docs: BEATGRID_IMPROVEMENTS.md, FEATURES_COMPLETED.md
- All features have built-in tooltips and help text

---

## 💾 Important

**Your data is safe:**
- All analysis stored in `config/meta.json`
- All tags stored locally
- Nothing uploaded anywhere
- You can always export to Rekordbox

**Back up your work:**
- `config/meta.json` contains everything
- `config/ui_settings.json` stores your preferences
- Keep these safe!

---

*Ready to dive in? Start with the Cues tab or AI Tags tab above!* 🎵
