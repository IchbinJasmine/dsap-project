"""
benchmark.py
艾森豪矩陣任務優先權決策引擎 — 效能基準測試

實驗目標：比較「傳統 List 線性掃描」與「Max-Heap」在
         連續提取 100 次最高優先任務時的時間複雜度差異。

執行方式：
    cd dsap-project/src
    python benchmark.py
"""

import sys
import time
import random
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from pathlib import Path

# ── 中文字型設定（macOS 使用 Heiti TC，Windows 備援 Microsoft YaHei）──
matplotlib.rcParams['font.sans-serif'] = [
    'Heiti TC', 'PingFang TC', 'Arial Unicode MS',
    'Microsoft YaHei', 'SimHei', 'sans-serif'
]
matplotlib.rcParams['axes.unicode_minus'] = False  # 避免負號顯示為方塊

# ── 將同目錄的 app.py 加入搜尋路徑 ──
sys.path.insert(0, str(Path(__file__).parent))
from app import Task, MaxHeap  # noqa: E402（路徑設定必須在 import 前）


# ══════════════════════════════════════════════════════════════
# 測試參數
# ══════════════════════════════════════════════════════════════

N_SIZES       = [100, 1_000, 10_000, 100_000]  # 四個資料量級
EXTRACT_COUNT = 100                              # 每輪連續提取次數
RANDOM_SEED   = 42                               # 固定亂數種子，確保兩組測試用相同資料集


# ══════════════════════════════════════════════════════════════
# 資料生成
# ══════════════════════════════════════════════════════════════

def generate_tasks(n: int, seed: int = RANDOM_SEED) -> list:
    """
    生成 n 筆假任務：
      - importance 與 urgency 均為 [1.0, 10.0] 的隨機浮點數
      - 固定 seed 讓 List 與 Heap 兩組測試使用完全相同的輸入資料
    """
    random.seed(seed)
    tasks = []
    for i in range(n):
        importance = round(random.uniform(1.0, 10.0), 2)
        urgency    = round(random.uniform(1.0, 10.0), 2)
        tasks.append(Task(name=f"T{i}", importance=importance, urgency=urgency))
    return tasks


# ══════════════════════════════════════════════════════════════
# 對照組：傳統 List 線性掃描  O(N) per extraction
# ══════════════════════════════════════════════════════════════

def benchmark_list(tasks: list, extract_count: int) -> float:
    """
    傳統 List 對照組的計時函式。

    演算法說明：
      每次提取 = 遍歷整個 list 找最大值 O(N)
               + list.pop(index) 搬移後半段   O(N)
      連續 extract_count 次 → 總計 O(extract_count × N)

    計時範圍：僅計算「連續 extract_count 次提取」的時間，
             不包含初始 list 的建立時間。
    """
    # shallow copy 即可，Task 物件本身不會被修改
    task_list = list(tasks)

    start = time.perf_counter()
    for _ in range(extract_count):
        if not task_list:
            break

        # ── O(N) 線性掃描：找出分數最高任務的索引 ──
        max_idx   = 0
        max_score = task_list[0].get_score()
        for j in range(1, len(task_list)):
            s = task_list[j].get_score()
            if s > max_score:
                max_score = s
                max_idx   = j

        # ── O(N) pop：list 需要搬移 max_idx 後方的所有元素 ──
        task_list.pop(max_idx)

    end = time.perf_counter()
    return end - start


# ══════════════════════════════════════════════════════════════
# 實驗組：Max-Heap  O(log N) per extraction
# ══════════════════════════════════════════════════════════════

def benchmark_heap(tasks: list, extract_count: int) -> float:
    """
    Max-Heap 實驗組的計時函式。

    演算法說明：
      建構 Heap（insert × N）→ 不計入計時
      每次提取 = extract_max() 呼叫一次
               根節點直接取出 O(1)，sift-down 修復 O(log N)
      連續 extract_count 次 → 總計 O(extract_count × log N)

    計時範圍：僅計算「連續 extract_count 次 extract_max()」的時間，
             建構期（insert loop）刻意排在 perf_counter 外。
    """
    # ── 建構期：insert 所有任務（不計入計時）──
    heap = MaxHeap()
    for t in tasks:
        heap.insert(t)

    # ── 計時期：純粹測量連續提取效能 ──
    start = time.perf_counter()
    for _ in range(extract_count):
        if not heap.heap:
            break
        heap.extract_max()  # O(log N)：根節點提取 + sift-down 修復
    end = time.perf_counter()

    return end - start


# ══════════════════════════════════════════════════════════════
# 主測試流程
# ══════════════════════════════════════════════════════════════

def run_benchmark():
    """
    依序對每個 N 值執行 List 與 Heap 的計時測試，
    回傳兩組耗時結果，並在終端印出對齊的比較表格。
    """
    list_times = []
    heap_times = []

    header = f"{'N':>10}  {'List (秒)':>12}  {'Heap (秒)':>12}  {'加速比':>8}"
    print(header)
    print("─" * len(header))

    for n in N_SIZES:
        tasks = generate_tasks(n)

        t_list = benchmark_list(tasks, EXTRACT_COUNT)
        t_heap = benchmark_heap(tasks, EXTRACT_COUNT)

        # 加速比：List 耗時 / Heap 耗時，數字越大表示 Heap 優勢越明顯
        speedup = t_list / t_heap if t_heap > 1e-9 else float('inf')

        list_times.append(t_list)
        heap_times.append(t_heap)

        print(f"{n:>10,}  {t_list:>12.6f}  {t_heap:>12.6f}  {speedup:>7.1f}×")

    return list_times, heap_times


# ══════════════════════════════════════════════════════════════
# 資料視覺化
# ══════════════════════════════════════════════════════════════

def plot_results(list_times: list, heap_times: list) -> None:
    """
    繪製折線圖，比較兩種方法在不同 N 下的耗時趨勢。

    設計說明：
      - X 軸使用對數座標（log scale）：讓 100~100,000 的寬跨度均勻展開，
        避免小 N 的資料點全部擠在左側。
      - Y 軸使用線性座標：直接呈現秒數，強調大 N 時 List 的耗時暴增。
      - 每個資料點標上實際秒數，方便報告引用。
    """
    fig, ax = plt.subplots(figsize=(11, 6.5))

    # ── 折線繪製 ──
    ax.plot(N_SIZES, list_times,
            'o-', color='#ef4444', linewidth=2.3, markersize=8,
            label=f'List 線性掃描  O(K·N)')
    ax.plot(N_SIZES, heap_times,
            's-', color='#4f46e5', linewidth=2.3, markersize=8,
            label=f'Max-Heap  O(K log N)')

    # ── 資料點標籤 ──
    # List 標籤放在點的上方（避免與 Heap 標籤重疊）
    for x, y in zip(N_SIZES, list_times):
        ax.annotate(
            f'{y:.5f}s',
            xy=(x, y), xytext=(0, 10),
            textcoords='offset points', ha='center',
            fontsize=8.5, color='#b91c1c',
            bbox=dict(boxstyle='round,pad=0.2', fc='#fef2f2', ec='#fecaca', alpha=0.8)
        )
    # Heap 標籤放在點的下方
    for x, y in zip(N_SIZES, heap_times):
        ax.annotate(
            f'{y:.5f}s',
            xy=(x, y), xytext=(0, -20),
            textcoords='offset points', ha='center',
            fontsize=8.5, color='#3730a3',
            bbox=dict(boxstyle='round,pad=0.2', fc='#eff6ff', ec='#bfdbfe', alpha=0.8)
        )

    # ── X 軸：對數座標，固定刻度顯示各 N 值 ──
    ax.set_xscale('log')
    ax.set_xticks(N_SIZES)
    ax.get_xaxis().set_major_formatter(
        ticker.FuncFormatter(lambda x, _: f'{int(x):,}')
    )
    ax.set_xlim(N_SIZES[0] * 0.6, N_SIZES[-1] * 1.6)

    # ── Y 軸：線性座標，下限設 0 讓差異更直觀 ──
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_formatter(
        ticker.FuncFormatter(lambda y, _: f'{y:.4f}')
    )

    # ── 標題與軸標籤 ──
    ax.set_xlabel('資料量 N（筆）', fontsize=12, labelpad=8)
    ax.set_ylabel(f'連續提取 {EXTRACT_COUNT} 次的總耗時（秒）', fontsize=12, labelpad=8)
    ax.set_title(
        f'Max-Heap vs List：連續提取最高優先任務 {EXTRACT_COUNT} 次的效能比較\n'
        '艾森豪矩陣任務優先權決策引擎（期末專題）',
        fontsize=13, fontweight='bold', pad=16
    )

    # ── 圖例與格線 ──
    ax.legend(fontsize=11, loc='upper left',
              framealpha=0.9, edgecolor='#e2e8f0')
    ax.grid(True, which='both', linestyle='--', linewidth=0.6, alpha=0.45)
    ax.set_facecolor('#f8fafc')
    fig.patch.set_facecolor('#ffffff')

    # ── 加速比標示文字（右上角） ──
    speedup_n_max = list_times[-1] / heap_times[-1] if heap_times[-1] > 1e-9 else 0
    ax.text(
        0.97, 0.95,
        f'N={N_SIZES[-1]:,} 時\nHeap 快 {speedup_n_max:.0f}×',
        transform=ax.transAxes,
        ha='right', va='top', fontsize=10, color='#1e293b',
        bbox=dict(boxstyle='round,pad=0.4', fc='#f1f5f9', ec='#cbd5e1', alpha=0.9)
    )

    plt.tight_layout()

    # ── 儲存圖片 ──
    out_path = Path(__file__).parent / 'benchmark_result.png'
    plt.savefig(out_path, dpi=150, bbox_inches='tight')
    print(f"\n圖表已儲存至：{out_path}")
    plt.show()


# ══════════════════════════════════════════════════════════════
# Entry Point
# ══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 55)
    print(" 艾森豪矩陣任務引擎 — 效能基準測試")
    print(f" 每個 N 值連續提取 {EXTRACT_COUNT} 次，使用 perf_counter() 計時")
    print("=" * 55)
    print()

    list_times, heap_times = run_benchmark()
    plot_results(list_times, heap_times)
