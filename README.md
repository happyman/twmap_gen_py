# twmap-gen — 地圖產生器 CLI 

[中文](#中文) | [English](#english)

---

## 中文

從各種地圖來源下載圖塊，拼接成有地理座標的馬賽克圖，匯出可列印的 PDF/KMZ/GeoTIFF 地圖（1:25,000 比例尺）。

### 功能特色

- 多種等高線地圖來源：魯地圖、經建三、NLSC、堡圖1904/1921、蕃地1916、陸測1924
- 輸出格式：PDF（多頁 A4/A3）、KMZ、GeoTIFF
- GPX 軌跡/航點疊加，支援海拔著色
- 100m/1000m 格線，標註 TWD97/TWD67 座標
- 灰階與彩色輸出模式
- 互動式 TUI（終端機介面）與桌面介面
- 區域範圍驗證（台灣本島 + 澎湖）
- 大範圍自動分塊處理

### 安裝

#### 一般使用者（下載 release）

從 [GitHub Releases](https://github.com/happyman/twmap_gen_py/releases) 下載最新版本的 zip 檔案，解壓縮後執行安裝腳本。

**Windows：**

1. 下載 `twmap_gen_py-win.zip`，解壓縮
2. 進入解壓縮後的資料夾，雙擊 `install.bat`
3. 安裝完成後，雙擊 `mapgen-tui.bat` 啟動

**Linux / macOS：**

```bash
unzip twmap_gen_py-*.zip
cd twmap_gen_py
./install.sh
./mapgen-tui.sh
```

#### 開發者（clone repo）

需要安裝 [git](https://git-scm.com/downloads)、Python 3.11+、[uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/happyman/twmap_gen_py.git
cd twmap_gen_py
./install.sh        # Linux / macOS
install.bat         # Windows
```

### 使用方式

**終端機介面（建議）：**

```bash
./mapgen-tui.sh     # Linux / macOS
mapgen-tui.bat      # Windows
```

**命令列：**

```bash
# 產生地圖（逗號格式：x0,y0 單位為公尺，shiftx/shifty 單位為公里）
uv run mapgen make --region 274000,2639000,3,3 --title "合歡山"

# 舊版冒號格式（startx/starty 單位為公里）
uv run mapgen make -r 274:2639:3:3 -t "合歡山"

# 搭配選項
uv run mapgen make -r 274:2639:3:3 -v 2016 -c -e --a3

# 列出可用的地圖來源
uv run mapgen list-sources
```

### 區域格式

**逗號格式（新版）：** `x0,y0,shiftx,shifty[,datum]`
- `x0,y0`：左上角座標，單位為**公尺**（TWD97 或 TWD67）
- `shiftx,shifty`：區域大小，單位為**公里**
- 範例：`274000,2639000,3,3` → 從 (274000, 2639000) 開始的 3×3 公里區域

**冒號格式（舊版）：** `x0:y0:shiftx:shifty:datum`
- `x0,y0`：左上角座標，單位為**公里**
- 範例：`274:2639:3:3:TWD97` → 同上的區域

### 地圖來源

| 代碼 | 名稱 | Zoom | px/km | 備註 |
|------|------|------|-------|------|
| `2016` | 魯地圖 | 16 | 315 | 預設，最完整 |
| `3` | 經建三 | 16 | 315 | 增強灰階 |
| `nlsc` | NLSC | 17 | 630 | 較高解析度 |
| `1904` | 堡圖1904 | 16 | 315 | 歷史地圖，適應性二值化 |
| `1916` | 蕃地1916 | 16 | 315 | 歷史地圖 |
| `1921` | 堡圖1921 | 16 | 315 | 歷史地圖，適應性二值化 |
| `1924` | 陸測1924 | 16 | 315 | 歷史地圖，適應性二值化 |

### 離開碼（Exit Codes）

| 代碼 | 意義 | Worker 動作 |
|------|------|------------|
| `0` | 成功 | 完成 |
| `1` | 暫時性錯誤（網路、圖塊、磁碟） | 重試 |
| `3` | 永久性輸入錯誤（區域超出範圍、檔案不存在） | **不重試** |
| `80` | 鍵盤中斷 | — |

後端 Worker 應檢查離開碼 `3`，**不**重試該任務，改為通知使用者。

### 設定

編輯 `config.toml` 進行自訂：(一般情況下不需更改)

```toml
[picker]
url = "https://twmap.happyman.idv.tw/map/?mode=picker&return=http://127.0.0.1:"
timeout = 300

[output]
font_path = ""  # 空字串使用內建 wqy-microhei.ttc
```

---

## English

Download slippy-map tiles from various Taiwan map sources, stitch them into georeferenced mosaics, and export printable PDF/KMZ/GeoTIFF maps at 1:25,000 scale.

### Features

- Multiple contour map sources: 魯地圖 (RudyMap), 經建三, NLSC, 堡圖1904/1921, 蕃地1916, 陸測1924
- Output formats: PDF (multi-page A4/A3), KMZ, GeoTIFF
- GPX track/waypoint overlay with elevation-colored tracks
- 100m/1000m grid lines with TWD97/TWD67 coordinate labels
- Grayscale and color output modes
- Interactive TUI (terminal UI) and desktop UI
- Region bounds validation (Taiwan + Penghu)
- Auto-chunking for large regions

### Installation

#### End Users (Download Release)

Download the latest zip from [GitHub Releases](https://github.com/happyman/twmap_gen_py/releases), extract, and run the install script.

**Windows:**

1. Download `twmap_gen_py-win.zip` and extract
2. Open the extracted folder and double-click `install.bat`
3. After installation, double-click `mapgen-tui.bat` to launch

**Linux / macOS:**

```bash
unzip twmap_gen_py-*.zip
cd twmap_gen_py
./install.sh
./mapgen-tui.sh
```

#### Developers (Clone Repo)

Requires [git](https://git-scm.com/downloads), Python 3.11+, [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/happyman/twmap_gen_py.git
cd twmap_gen_py
./install.sh        # Linux / macOS
install.bat         # Windows
```

### Usage

**Terminal UI (recommended):**

```bash
./mapgen-tui.sh     # Linux / macOS
mapgen-tui.bat      # Windows
```

**Command line:**

```bash
# Generate a map (comma format: x0,y0 in metres, shiftx/shifty in km)
uv run mapgen make --region 274000,2639000,3,3 --title "合歡山"

# Legacy colon format (startx/starty in km)
uv run mapgen make -r 274:2639:3:3 -t "合歡山"

# With options
uv run mapgen make -r 274:2639:3:3 -v 2016 -c -e --a3

# List available map sources
uv run mapgen list-sources
```

### Region Format

**Comma format (modern):** `x0,y0,shiftx,shifty[,datum]`
- `x0,y0`: top-left corner in **metres** (TWD97 or TWD67)
- `shiftx,shifty`: region size in **kilometres**
- Example: `274000,2639000,3,3` → 3×3 km region starting at (274000, 2639000)

**Colon format (legacy):** `x0:y0:shiftx:shifty:datum`
- `x0,y0`: top-left corner in **kilometres**
- Example: `274:2639:3:3:TWD97` → same region as above

### Map Sources

| Key | Label | Zoom | px/km | Notes |
|-----|-------|------|-------|-------|
| `2016` | 魯地圖 | 16 | 315 | Default, most complete |
| `3` | 經建三 | 16 | 315 | Enhanced grayscale |
| `nlsc` | NLSC | 17 | 630 | Higher resolution |
| `1904` | 堡圖1904 | 16 | 315 | Historical, adaptive threshold |
| `1916` | 蕃地1916 | 16 | 315 | Historical |
| `1921` | 堡圖1921 | 16 | 315 | Historical, adaptive threshold |
| `1924` | 陸測1924 | 16 | 315 | Historical, adaptive threshold |

### Exit Codes

| Code | Meaning | Worker Action |
|------|---------|---------------|
| `0` | Success | Done |
| `1` | Transient error (network, tiles, disk) | Retry |
| `3` | Permanent input error (bad region, missing file) | **No retry** |
| `80` | Keyboard interrupt | — |

The backend worker should check exit code `3` and **not** retry the job — notify the user instead.

### Configuration

Edit `config.toml` to customize:(normally nothing to change)

```toml
[picker]
url = "https://twmap.happyman.idv.tw/map/?mode=picker&return=http://127.0.0.1:"
timeout = 300

[output]
font_path = ""  # Empty uses bundled wqy-microhei.ttc
```

### License

MIT
