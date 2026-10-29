#!/bin/bash
# Bifang Demo Video Build Script
# Generates demo video from HTML scenes + narration using playwright + edge-tts + ffmpeg

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENES_DIR="$SCRIPT_DIR/scenes"
NARRATION_DIR="$SCRIPT_DIR/narration"
FRAMES_DIR="$SCRIPT_DIR/frames"
AUDIO_DIR="$SCRIPT_DIR/audio"
OUTPUT_FILE="$SCRIPT_DIR/output.mp4"

# Scene order and durations (in seconds) from scenes.json
SCENES=(
  "01-hook:4"
  "02-problem:5"
  "03-solution:6"
  "04-demo-inspect:5"
  "05-demo-propose:5"
  "06-demo-approve:5"
  "07-demo-verify:5"
  "08-features:5"
  "09-cta:5"
)

# Check for required tools
check_tool() {
  if ! command -v "$1" &> /dev/null; then
    echo "❌ $1 not found. Please install it."
    return 1
  fi
  echo "✅ $1 found"
}

echo "🔍 Checking required tools..."
check_tool playwright || true
check_tool edge-tts || true
check_tool ffmpeg || true
check_tool python3 || true

# Create directories
mkdir -p "$FRAMES_DIR" "$AUDIO_DIR"

# Step 1: Capture frames from HTML scenes using playwright
echo "📸 Capturing frames from HTML scenes..."
for scene_spec in "${SCENES[@]}"; do
  scene_id="${scene_spec%%:*}"
  duration="${scene_spec##*:}"
  
  echo "  Capturing $scene_id (${duration}s)..."
  
  # Use playwright to capture a frame from the HTML scene
  if command -v playwright &> /dev/null; then
    playwright install chromium >/dev/null 2>&1 || true
    npx playwright screenshot \
      --device="Desktop Chrome" \
      --viewport="1920,1080" \
      "$SCENES_DIR/$scene_id.html" \
      "$FRAMES_DIR/$scene_id.png" 2>/dev/null || {
      echo "  ⚠️  Playwright capture failed for $scene_id. Creating placeholder..."
      # Create a simple placeholder using ImageMagick if available
      if command -v convert &> /dev/null; then
        convert -size 1920x1080 xc:'#0F172A' \
          -font "DejaVu-Sans-Bold" -pointsize 48 -fill "#FF8A3D" \
          -gravity center -annotate +0+0 "$scene_id" \
          "$FRAMES_DIR/$scene_id.png" 2>/dev/null || true
      fi
    }
  else
    echo "  ⚠️  Playwright not available. Creating placeholder..."
    if command -v convert &> /dev/null; then
      convert -size 1920x1080 xc:'#0F172A' \
        -font "DejaVu-Sans-Bold" -pointsize 48 -fill "#FF8A3D" \
        -gravity center -annotate +0+0 "$scene_id" \
        "$FRAMES_DIR/$scene_id.png" 2>/dev/null || true
    fi
  fi
done

# Step 2: Generate audio from narration text using edge-tts
echo "🎙️ Generating narration audio..."
for scene_spec in "${SCENES[@]}"; do
  scene_id="${scene_spec%%:*}"
  duration="${scene_spec##*:}"
  
  narration_file="$NARRATION_DIR/$scene_id.txt"
  audio_file="$AUDIO_DIR/$scene_id.mp3"
  
  if [[ -f "$narration_file" ]]; then
    text="$(cat "$narration_file")"
    echo "  Generating audio for $scene_id..."
    
    if command -v edge-tts &> /dev/null; then
      edge-tts --voice "en-US-AndrewNeural" --rate="+0%" --volume="+0%" \
        --text "$text" --write-media "$audio_file" 2>/dev/null || {
        echo "  ⚠️  edge-tts failed for $scene_id"
      }
    else
      echo "  ⚠️  edge-tts not available. Skipping audio generation."
      # Create silent audio placeholder
      if command -v ffmpeg &> /dev/null; then
        ffmpeg -f lavfi -i "anullsrc=r=44100:cl=stereo" -t "$duration" -c:a libmp3lame "$audio_file" -y -loglevel quiet 2>/dev/null || true
      fi
    fi
  else
    echo "  ⚠️  No narration file for $scene_id"
  fi
done

# Step 3: Composite video with ffmpeg
echo "🎬 Compositing video..."
if command -v ffmpeg &> /dev/null; then
  # Build filter complex for concatenation with crossfades
  FILTER_COMPLEX=""
  INPUTS=""
  CURRENT_TIME=0
  
  for i in "${!SCENES[@]}"; do
    scene_spec="${SCENES[i]}"
    scene_id="${scene_spec%%:*}"
    duration="${scene_spec##*:}"
    
    INPUTS="$INPUTS -loop 1 -t $duration -i $FRAMES_DIR/$scene_id.png"
    
    if [[ -f "$AUDIO_DIR/$scene_id.mp3" ]]; then
      INPUTS="$INPUTS -i $AUDIO_DIR/$scene_id.mp3"
    fi
  done
  
  # Build video filter: concat frames with crossfade
  VIDEO_FILTER=""
  AUDIO_FILTER=""
  for i in "${!SCENES[@]}"; do
    scene_spec="${SCENES[i]}"
    duration="${scene_spec##*:}"
    
    if [[ $i -eq 0 ]]; then
      VIDEO_FILTER="[0:v]trim=duration=$duration,setpts=PTS-STARTPTS[v$i]"
      AUDIO_FILTER="[${#SCENES[@]}*2]:a]atrim=duration=$duration,asetpts=PTS-STARTPTS[a$i]"
    else
      VIDEO_FILTER="$VIDEO_FILTER;[$i:v]trim=duration=$duration,setpts=PTS-STARTPTS[v$i]"
      AUDIO_FILTER="$AUDIO_FILTER;[${#SCENES[@]}*2+i:a]atrim=duration=$duration,asetpts=PTS-STARTPTS[a$i]"
    fi
  done
  
  # Concatenate video and audio
  VIDEO_CONCAT=""
  AUDIO_CONCAT=""
  for i in "${!SCENES[@]}"; do
    VIDEO_CONCAT="$VIDEO_CONCAT[v$i]"
    AUDIO_CONCAT="$AUDIO_CONCAT[a$i]"
  done
  VIDEO_CONCAT="$VIDEO_CONCAT concat=n=${#SCENES[@]}:v=1:a=0[outv]"
  AUDIO_CONCAT="$AUDIO_CONCAT concat=n=${#SCENES[@]}:v=0:a=1[outa]"
  
  FILTER_COMPLEX="$VIDEO_FILTER; $AUDIO_FILTER; $VIDEO_CONCAT; $AUDIO_CONCAT"
  
  echo "  Running ffmpeg..."
  ffmpeg $INPUTS \
    -filter_complex "$FILTER_COMPLEX" \
    -map "[outv]" -map "[outa]" \
    -c:v libx264 -preset medium -crf 18 \
    -c:a aac -b:a 192k \
    -pix_fmt yuv420p \
    -movflags +faststart \
    "$OUTPUT_FILE" -y -loglevel warning
  
  if [[ $? -eq 0 ]]; then
    echo "✅ Video created: $OUTPUT_FILE"
    ls -lh "$OUTPUT_FILE"
  else
    echo "❌ ffmpeg failed"
    exit 1
  fi
else
  echo "❌ ffmpeg not available. Cannot composite video."
  echo "   Manual command to run:"
  echo "   ffmpeg -f concat -safe 0 -i <(for f in $FRAMES_DIR/*.png; do echo \"file '\$f'\"; done) -c:v libx264 -pix_fmt yuv420p $OUTPUT_FILE"
  exit 1
fi

echo "🎉 Build complete! Output: $OUTPUT_FILE"