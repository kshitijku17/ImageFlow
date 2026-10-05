# 🌊 ImageFlow

**ImageFlow** is a modern, high-performance desktop application designed for photographers and digital media managers to rapidly review, select, organize, and manage large collections of images. Powered by **PySide6** and **OpenCLIP AI**, ImageFlow brings modern natural-language semantic search, visual similarity matching, and intelligent date filtering directly to local photo libraries.

---

## 🎓 College Group Project

This application was developed as a college group project by:
- **Kshitij Kumar** (`GF202570272`)
- **Palak Sharma** (`GF202564556`)

---

## ✨ Features

- **⚡ Lightning-Fast Image Review & Organization**
  - Instant image preview and full-screen viewer with zoom, pan, and rotation.
  - Quick action buttons to copy, move, or delete selected photos.
  - Multi-select thumbnails with keyboard navigation shortcuts.

- **🤖 AI-Powered Semantic Image Search (OpenCLIP)**
  - Natural Language Queries: Search for abstract concepts like *"sunset over beach"*, *"dog playing in grass"*, or *"red sports car"*.
  - No cloud connection required: CLIP vector embeddings are computed 100% locally.

- **🖼️ Visual Reference Image Search**
  - Drag and drop or select a reference image to find visually similar photos across your library.

- **📅 Natural Language Date & Metadata Filtering**
  - Smart Date Parser: Recognizes queries such as *"photos from 10 December 2025"*, *"pictures taken in June 2024"*, or *"dog photos from Dec 2025"*.
  - EXIF Timestamp Priority: Extracts `DateTimeOriginal` from EXIF tags with fallback to filesystem modification timestamps (`mtime`).

- **⚡ Incremental Vector Indexing & ChromaDB Storage**
  - Local **ChromaDB** vector database persists embeddings.
  - Automatic change detection skips unchanged files and indexes only new or modified images.

- **🎨 Themes & Customization**
  - Includes modern Light, Dark, Cyberpunk, and Classic GUI themes built with custom PySide6 styling.

---

## 🛠️ Tech Stack

| Domain | Technology / Library | Description |
| :--- | :--- | :--- |
| **GUI Framework** | `PySide6` (Qt 6) | Desktop UI layout, thumbnail bars, viewer, dialogs, dark/light themes |
| **AI / Embeddings** | `torch`, `open_clip_torch` | PyTorch runtime with OpenCLIP `ViT-B-32` model |
| **Vector Database** | `chromadb` | Local persistent vector storage for high-speed similarity search |
| **Image Engine** | `Pillow` (PIL) | Image loading, resizing, rotation, EXIF metadata extraction |
| **Language & Runtime** | `Python 3.10+` | Core application logic & thread-safe worker pools |

---

## 📂 Project Structure

```text
ImageFlow/
├── main.py                    # Application entry point
├── requirements.txt           # Python dependencies
├── README.md                  # Project documentation & overview
├── .gitignore                 # Git ignore rules
│
├── ai/                        # AI Engine & Vector Search
│   ├── chroma_manager.py      # ChromaDB collection & persistent vector storage
│   ├── clip_manager.py        # OpenCLIP ViT-B-32 model loader & embedding generator
│   ├── date_parser.py        # Natural language date extractor & filter parser
│   ├── indexer.py             # Image metadata scanner & incremental indexer
│   └── search.py              # Semantic & reference image similarity search API
│
├── core/                      # Application Logic & Data Layer
│   ├── file_operations.py     # File copy, move, delete operations with unique naming
│   ├── folder_manager.py      # Source/destination directory scanner & monitor
│   ├── image_manager.py       # Image collection state & selection management
│   ├── navigation.py         # Thumbnail navigation & bounds handling
│   └── slideshow.py          # Automatic slideshow playback timer
│
├── ui/                        # PySide6 User Interface Components
│   ├── main_window.py         # Main application window & toolbar integration
│   ├── ai_window.py           # AI Search Assistant dialog & prompt bar
│   ├── dialogs.py             # Settings, confirmation, and file dialogs
│   ├── fullscreen_viewer.py   # Fullscreen borderless viewer window
│   ├── image_viewer.py        # Interactive main canvas with zoom/pan capabilities
│   ├── theme.py               # Application theme stylesheets (White, Dark, Cyberpunk)
│   ├── thumbnail_bar.py       # Scrollable thumbnail bar with caching
│   ├── timeline.py            # Date timeline navigation widget
│   └── toolbar.py             # Top action bar and buttons
│
├── utils/                     # Helpers & System Constants
│   ├── constants.py           # Global constants, extensions, cache limits, DB paths
│   └── helpers.py             # Utility functions (unique filename generation, etc.)
│
├── workers/                   # Asynchronous Thread Workers (QThread)
│   ├── image_loader.py        # Asynchronous full-resolution image loader
│   ├── indexer_worker.py      # Background AI indexing thread
│   ├── thumbnail_worker.py    # Background thumbnail generation thread
│   └── worker.py              # Generic Qt worker thread wrapper
│
├── config/                    # Application Configuration
│   └── settings.py            # User settings persistent JSON manager
│
├── docs/                      # Documentation & System Architecture
│   └── Requirements.txt       # Project requirements & architectural plan
│
├── scripts/                   # Maintenance & Build Scripts
│   └── create_zip.py          # Project packaging & ZIP archive builder
│
└── tests/                     # Comprehensive Unit & Integration Test Suite
    ├── test_ai_clip.py                # Tests OpenCLIP model load & embeddings
    ├── test_ai_date_filter.py         # Tests EXIF date priority & date search
    ├── test_ai_full_integration.py    # Tests end-to-end AI search workflow
    ├── test_ai_indexing.py            # Tests incremental indexing & ChromaDB storage
    ├── test_ai_reference_search.py   # Tests visual image-to-image similarity search
    └── test_ai_search.py              # Tests natural language query matching
```

---

## 🚀 Setup & Installation

### 1. Prerequisites
- **Python 3.10+** installed on your system.
- NVIDIA GPU (optional, for CUDA-accelerated OpenCLIP inference; CPU is fully supported).

### 2. Clone the Repository
```bash
git clone https://github.com/kshitijku17/ImageFlow.git
cd ImageFlow
```

### 3. Create a Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## 💻 Usage

Run the desktop application from the root directory:

```bash
python main.py
```

### Quick Start Guide
1. **Select Source Folder**: Click **Open Folder** or press `Ctrl+O` to load images into ImageFlow.
2. **Review & Navigate**: Use the left/right arrow keys or mouse wheel to navigate between photos.
3. **Organize Photos**: Click **Copy** or **Move** to transfer selected images into your target destination directory.
4. **AI Assistant**: Press `Ctrl+F` or click **AI Search** to launch the AI search window.
5. **Natural Language Search**: Enter queries like *"family at sunset"* or *"photos from December 2025"* to filter your library instantly.

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| `Left Arrow` / `A` | Previous Image |
| `Right Arrow` / `D` | Next Image |
| `Ctrl + O` | Open Source Folder |
| `Ctrl + Shift + O` | Set Destination Folder |
| `Ctrl + F` | Open AI Search Dialog |
| `F11` / `Double Click` | Toggle Fullscreen Mode |
| `Y` / `Ctrl + C` | Copy Image to Destination |
| `M` / `Ctrl + M` | Move Image to Destination |
| `Delete` / `Backspace` | Delete Image (with confirmation) |
| `Space` | Toggle Slideshow |
| `+` / `-` / `Scroll Wheel` | Zoom In / Zoom Out |
| `R` | Rotate Image |
| `Escape` | Exit Fullscreen / Close Dialog |

---

## 🧪 Running Tests

All test suites are located in the `tests/` directory and run self-contained isolated tests:

```bash
# Run all tests via Python unittest module
python -m unittest discover tests

# Or run individual test scripts
python tests/test_ai_clip.py
python tests/test_ai_indexing.py
python tests/test_ai_search.py
python tests/test_ai_date_filter.py
python tests/test_ai_reference_search.py
python tests/test_ai_full_integration.py
```

---

## 🔮 Future Scope

- [ ] **Face Recognition & Clustering**: Group photos automatically by people recognized in images.
- [ ] **Duplicate & Near-Duplicate Detection**: Detect duplicate images based on vector similarity thresholds.
- [ ] **Batch Metadata & Tagging**: Add custom tags, ratings (1-5 stars), and EXIF editing.
- [ ] **Export & Presentation Reports**: Export selected collections to PDF contact sheets or slideshow videos.
- [ ] **Cloud Backup Sync**: Optional encrypted backup to cloud storage (Google Drive, S3).

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for details.
