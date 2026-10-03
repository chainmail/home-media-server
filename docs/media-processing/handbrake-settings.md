# Configuration Blueprint: Headless HandBrakeCLI Quality Profiles
**Source Ingest Engine:** Raw Uncompressed MakeMKV Remux Outputs  
**Primary Language Target:** English (`eng`)  
**Encoding Framework:** Architecture Optimized Software Compute  

---

## 1. Audio and Video Codec Recommendations

When processing files natively on the **Raspberry Pi 5 CPU cores**, we divide the presets into two separate profiles depending on the generation of the optical source disk:

### 1.1 DVD Sources (Standard Definition - 480p/576p)
*   **Video Codec:** Standard **H.264 (`x264`)**. 
*   **Why?** DVDs are standard definition. Encoding them with H.264 is incredibly fast on the Pi 5 and achieves maximum device compatibility without losing detail. 
*   **Quality Target (CRF):** `19`. Lower values mean higher quality; `19` strikes the perfect balance where the compressed output looks identical to the original disk.
*   **Filters:** DVDs are almost always **interlaced** (which causes jagged horizontal lines during motion). The `--yadif` filter cleans this up completely.

### 1.2 Blu-ray Sources (High Definition - 1080p)
*   **Video Codec:** Modern **H.265 10-bit (`x265_10bit`)**.
*   **Why?** Blu-rays hold massive amounts of data. H.265 10-bit yields highly compact files, eliminates color banding in dark scenes, and compresses 1080p files far better than H.264.
*   **Quality Target (CRF):** `22`. This value provides pristine high-definition playback while saving immense storage space on your NAS.

---

## 2. Runtime Command Arguments

### 2.1 Optimization Profiles for DVDs
Replace the generic execution line inside your automated container runner scripts with this exact production argument structure:

```bash
HandBrakeCLI -i "$INPUT_TARGET" -o "$OUTPUT_TARGET" \
  -e x264 \
  -q 19 \
  --encoder-preset medium \
  --comb-detect --yadif=default \
  --audio-lang-list eng \
  --aencoder copy \
  --audio-fallback ffac3 \
  --subtitle-lang-list eng \
  --first-audio
```

### 2.2 Optimization Profiles for Blu-rays
Use this argument matrix for high-definition 1080p processing nodes:

```bash
HandBrakeCLI -i "$INPUT_TARGET" -o "$OUTPUT_TARGET" \
  -e x265_10bit \
  -q 22 \
  --encoder-preset medium \
  --audio-lang-list eng \
  --aencoder copy \
  --audio-fallback ffac3 \
  --subtitle-lang-list eng \
  --first-audio
```

---

## 3. Argument Reference

To understand how HandBrake is handling your movie files, here is exactly what these arguments instruct the cluster to do:

*   **`-e x265_10bit` / `-e x264`**: Selects the exact mathematical engine processing the video compression track frames.
*   **`-q 22` / `-q 19`**: **Constant Rate Factor (CRF)**. This tells HandBrake to prioritize visual quality over exact file size. It allocates more data blocks to fast-moving action scenes and drops data budgets during static scenes, ensuring a uniform visual presentation.
*   **`--encoder-preset medium`**: Controls the computational efficiency balance. "Medium" balances file compression size against encoding speed, which is optimal for the Pi 5's Cortex-A76 cores.
*   **`--audio-lang-list eng`**: Scans the MakeMKV source file and explicitly discards foreign audio tracks (commentaries, alternate dubs), saving space.
*   **`--aencoder copy`**: **Direct Pass-through**. Instead of wasting CPU power compressing the audio track (which degrades sound quality), HandBrake completely copies the original high-fidelity English Dolby Digital or DTS soundtrack directly into the new file.
*   **`--audio-fallback ffac3`**: If the source audio tracks are stored in an exotic format that cannot be directly copied, this converts the track to standard high-compatibility AC3 audio.
*   **`--subtitle-lang-list eng`**: Automatically extracts the English subtitle layers, ignoring alternative languages.
*   **`--first-audio`**: Selects the primary English track as the default playback channel, so the movie plays in English immediately without you having to manually toggle options in your media player.

