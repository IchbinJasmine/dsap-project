import json
import uuid
import cmd
from datetime import datetime
from pathlib import Path

class Task:
    def __init__(self, name, importance, urgency=None, deadline=None, created_at=None, task_id=None):
        self.id = task_id or str(uuid.uuid4())[:6]
        self.name = name
        self.importance = max(1, min(10, float(importance))) # 1-10
        
        self.created_at = datetime.fromisoformat(created_at) if created_at else datetime.now()
        self.deadline = datetime.fromisoformat(deadline) if deadline else None
        
        # 若有設定 deadline，系統自動轉換為緊急度；否則使用手動輸入的緊急度
        if self.deadline:
            self.urgency = self._calculate_urgency()
        else:
            self.urgency = max(1, min(10, float(urgency or 1)))

    def _calculate_urgency(self):
        """將 Deadline 線性轉換為緊急度 (1-10)"""
        if not self.deadline:
            return 1.0
        now = datetime.now()
        if self.deadline <= now:
            return 10.0 # 已經過期，緊急度拉滿
            
        hours_left = (self.deadline - now).total_seconds() / 3600
        # 假設大於 14 天 (336小時) 為最低緊急度 1，24小時內為最高 10
        if hours_left >= 336:
            return 1.0
        elif hours_left <= 24:
            return 10.0
        else:
            # 線性轉換
            return 10.0 - ((hours_left - 24) * (9.0 / 312))

    def get_score(self):
        """
        計算綜合權重：
        基礎分數 = (重要性 * 1.5) + 緊急度
        老化機制 (Aging) = 任務每存活 1 天，分數增加 0.5 (防止 Starvation)
        """
        # 動態更新因 deadline 產生的 urgency
        if self.deadline:
            self.urgency = self._calculate_urgency()
            
        base_score = (self.importance * 1.5) + self.urgency
        days_alive = (datetime.now() - self.created_at).total_seconds() / 86400
        aging_bonus = days_alive * 0.5
        
        return base_score + aging_bonus

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "importance": self.importance,
            "urgency": self.urgency,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "created_at": self.created_at.isoformat()
        }

class MaxHeap:
    def __init__(self):
        self.heap = []
        self.pos_map = {} # Hash Table: task_id -> index 達成 O(1) 尋址

    def peek_max(self):
        """O(1) 取得當前最高優先任務但不移除"""
        return self.heap[0] if self.heap else None

    def _swap(self, i, j):
        self.heap[i], self.heap[j] = self.heap[j], self.heap[i]
        self.pos_map[self.heap[i].id] = i
        self.pos_map[self.heap[j].id] = j

    def _sift_up(self, i):
        parent = (i - 1) // 2
        while i > 0 and self.heap[i].get_score() > self.heap[parent].get_score():
            self._swap(i, parent)
            i = parent
            parent = (i - 1) // 2

    def _sift_down(self, i):
        n = len(self.heap)
        while True:
            largest = i
            left = 2 * i + 1
            right = 2 * i + 2

            if left < n and self.heap[left].get_score() > self.heap[largest].get_score():
                largest = left
            if right < n and self.heap[right].get_score() > self.heap[largest].get_score():
                largest = right

            if largest != i:
                self._swap(i, largest)
                i = largest
            else:
                break

    def insert(self, task):
        """O(log N) 插入新任務"""
        self.heap.append(task)
        idx = len(self.heap) - 1
        self.pos_map[task.id] = idx
        self._sift_up(idx)

    def extract_max(self):
        """O(1) 提取並 O(log N) 重構"""
        if not self.heap:
            return None
        max_task = self.heap[0]
        last_task = self.heap.pop()
        del self.pos_map[max_task.id]
        
        if self.heap:
            self.heap[0] = last_task
            self.pos_map[last_task.id] = 0
            self._sift_down(0)
            
        return max_task

    def remove_by_id(self, task_id):
        """O(log N) 依任務 ID 刪除指定任務"""
        idx = self.pos_map.get(task_id)
        if idx is None:
            return None

        removed_task = self.heap[idx]
        last_idx = len(self.heap) - 1

        if idx == last_idx:
            self.heap.pop()
            del self.pos_map[removed_task.id]
            return removed_task

        last_task = self.heap.pop()
        del self.pos_map[removed_task.id]
        self.heap[idx] = last_task
        self.pos_map[last_task.id] = idx

        parent = (idx - 1) // 2
        if idx > 0 and self.heap[idx].get_score() > self.heap[parent].get_score():
            self._sift_up(idx)
        else:
            self._sift_down(idx)

        return removed_task

    def refresh(self):
        """
        因時間推移導致 Aging 與 Deadline 分數變動，觸發全域重構。
        此為 O(N) 操作，僅在使用者要求印出最新列表時觸發。
        """
        n = len(self.heap)
        for i in range(n // 2 - 1, -1, -1):
            self._sift_down(i)

    def update_task(self, task_id, new_importance=None, new_urgency=None, new_deadline=None):
        """
        O(log N) 就地更新任務屬性並恢復 Max-Heap 性質。

        演算法流程：
          1. O(1) 查詢 pos_map，直接取得該任務在陣列中的 index，
             完全不需要 O(N) 的線性掃描。
          2. 記錄更新前的舊分數，作為後續判斷 sift 方向的基準。
          3. 套用新屬性（importance / urgency / deadline）。
          4. 比較新舊分數：
             - 新 > 舊 → 節點「上升」，可能違反「父 ≥ 子」性質 → _sift_up
             - 新 < 舊 → 節點「下降」，可能違反「節點 ≥ 子」性質 → _sift_down
             - 新 = 舊 → Heap 結構未被破壞，直接跳過
          每次 sift 最多走 O(log N) 層，整體時間複雜度為 O(log N)。
        """
        # Step 1: O(1) 定位 ── 查 Hash Table，跳過任何線性掃描
        idx = self.pos_map.get(task_id)
        if idx is None:
            return None  # 任務不存在，直接返回

        task = self.heap[idx]

        # Step 2: 快照舊分數，供後續比較（在修改屬性前先呼叫）
        old_score = task.get_score()

        # Step 3: 套用新屬性
        if new_importance is not None:
            task.importance = max(1, min(10, float(new_importance)))

        if new_deadline is not None:
            # 設定新 deadline，並立即重新計算緊急度
            task.deadline = datetime.fromisoformat(new_deadline)
            task.urgency = task._calculate_urgency()
        elif new_urgency is not None:
            # 切換為手動緊急度模式，同時清除舊 deadline
            task.deadline = None
            task.urgency = max(1, min(10, float(new_urgency)))

        # Step 4: 計算新分數，並決定 sift 方向
        new_score = task.get_score()

        if new_score > old_score:
            # 分數上升：節點優先度增加，可能比父節點高，需向上修復
            self._sift_up(idx)
        elif new_score < old_score:
            # 分數下降：節點優先度降低，可能比子節點低，需向下修復
            self._sift_down(idx)
        # 分數相同：Heap 性質仍然成立，無須任何操作

        return task

class EisenhowerEngineCLI(cmd.Cmd):
    intro = '歡迎使用艾森豪矩陣任務優先權決策引擎 (輸入 help 查看指令)'
    prompt = '(Engine) > '

    def __init__(self):
        super().__init__()
        self.heap = MaxHeap()
        self.data_file = Path(__file__).with_name('tasks_data.json')
        self.current_task_id = None

    def do_add(self, arg):
        """
        新增任務
        用法: add <任務名稱> <重要性1-10> <緊急度1-10或Deadline YYYY-MM-DD>
        範例1: add 寫專題報告 9 8
        範例2: add 繳交水電費 5 2024-06-30
        """
        args = arg.split()
        if len(args) < 3:
            print("❌ 參數錯誤。用法: add <名稱> <重要度> <緊急度/日期>")
            return
            
        name = args[0]
        try:
            importance = float(args[1])
            urgency_or_date = args[2]
            
            if "-" in urgency_or_date:
                # 判斷為日期字串
                task = Task(name=name, importance=importance, deadline=urgency_or_date)
            else:
                # 判斷為直接評分
                task = Task(name=name, importance=importance, urgency=float(urgency_or_date))
                
            self.heap.insert(task)
            print(f"✅ 任務 [{task.name}] 已加入，初始權重分數: {task.get_score():.2f}")
        except ValueError:
            print("❌ 日期格式請使用 YYYY-MM-DD，或確保重要度/緊急度為數字。")

    def do_next(self, arg):
        """O(1) 查看當下最高優先權任務（不刪除）"""
        # 查看前先更新一次老化狀態以確保精準
        self.heap.refresh()
        task = self.heap.peek_max()
        if not task:
            self.current_task_id = None
            print("🎉 當前無待辦任務！")
        else:
            self.current_task_id = task.id
            print(f"🔥 [最高優先執行] {task.name} (ID: {task.id}) | 綜合權重: {task.get_score():.2f}")
            print("✅ 完成後請輸入 done 來刪除這個任務。")

    def do_done(self, arg):
        """完成目前任務並刪除（需先使用 next 指定）"""
        if not self.heap.heap:
            self.current_task_id = None
            print("🎉 當前無待辦任務！")
            return

        if not self.current_task_id:
            print("⚠️ 尚未指定目前任務，請先輸入 next。")
            return

        removed = self.heap.remove_by_id(self.current_task_id)
        if not removed:
            self.current_task_id = None
            print("⚠️ 目前任務不存在，請重新輸入 next。")
            return

        print(f"✅ 已完成並刪除任務：{removed.name} (ID: {removed.id})")
        self.current_task_id = None

    def do_list(self, arg):
        """列出當前所有任務 (會先觸發權重更新)"""
        if not self.heap.heap:
            print("📭 清單為空。")
            return
            
        self.heap.refresh()
        # 暫時複製並排序以利顯示，不影響底層結構
        sorted_tasks = sorted(self.heap.heap, key=lambda x: x.get_score(), reverse=True)
        
        print(f"{'ID':<8} | {'任務名稱':<15} | {'重要度':<6} | {'緊急度':<6} | {'綜合權重':<8}")
        print("-" * 55)
        for t in sorted_tasks:
            urg_str = f"{t.urgency:.1f}"
            if t.deadline:
                urg_str += "(DL)"
            print(f"{t.id:<8} | {t.name:<15} | {t.importance:<6.1f} | {urg_str:<6} | {t.get_score():<8.2f}")

    def do_save(self, arg):
        """資料持久化：將狀態匯出為 JSON"""
        data = [t.to_dict() for t in self.heap.heap]
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"💾 已將 {len(data)} 筆任務儲存至 {self.data_file.name}")

    def do_load(self, arg):
        """匯入 JSON 資料"""
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.heap = MaxHeap() # 重置
                for d in data:
                    t = Task(
                        name=d['name'], 
                        importance=d['importance'], 
                        urgency=d['urgency'], 
                        deadline=d['deadline'][:10] if d['deadline'] else None,
                        created_at=d['created_at'],
                        task_id=d['id']
                    )
                    self.heap.insert(t)
            print(f"📂 成功載入 {len(data)} 筆任務！")
        except FileNotFoundError:
            print("❌ 找不到存檔檔案。")

    def do_edit(self, arg):
        """
        編輯指定任務的重要度與緊急度/Deadline，並以 O(log N) 調整 Heap 位置。
        用法: edit <task_id> <新的重要度> <新的緊急度或Deadline>
        範例1: edit abc123 9 7
        範例2: edit abc123 9 2025-07-15
        """
        args = arg.split()
        if len(args) < 3:
            print("❌ 參數錯誤。用法: edit <task_id> <重要度> <緊急度/日期>")
            return

        task_id = args[0]

        # O(1) 預先確認任務是否存在，避免無效的後續操作
        if task_id not in self.heap.pos_map:
            print(f"❌ 找不到 ID 為 [{task_id}] 的任務，請用 list 確認 ID。")
            return

        try:
            new_importance = float(args[1])
            urgency_or_date = args[2]

            if "-" in urgency_or_date:
                # 包含「-」→ 視為日期格式，轉為 deadline
                updated = self.heap.update_task(
                    task_id,
                    new_importance=new_importance,
                    new_deadline=urgency_or_date
                )
            else:
                # 純數字 → 視為手動緊急度
                updated = self.heap.update_task(
                    task_id,
                    new_importance=new_importance,
                    new_urgency=float(urgency_or_date)
                )

            if updated:
                deadline_str = (f" (Deadline: {updated.deadline.strftime('%Y-%m-%d')})"
                                if updated.deadline else "")
                print(f"✅ 任務 [{updated.name}] 已更新！新綜合權重: {updated.get_score():.2f}")
                print(f"   重要度: {updated.importance:.1f} | 緊急度: {updated.urgency:.1f}{deadline_str}")
            else:
                print("❌ 更新失敗，請確認 task_id 是否正確。")

        except ValueError:
            print("❌ 日期格式請使用 YYYY-MM-DD，或確保重要度/緊急度為數字。")

    def do_matrix(self, _):
        """
        以艾森豪四象限矩陣視覺化當前所有任務。
        重要度 >= 5 視為「重要」，緊急度 >= 5 視為「緊急」。
        有 Deadline 的任務會即時呼叫 _calculate_urgency() 取得動態緊急度。
        """
        if not self.heap.heap:
            print("📭 清單為空，無法顯示矩陣。")
            return

        THRESHOLD = 5        # 重要度與緊急度的分水嶺
        MAX_PER_Q = 5        # 每象限最多顯示幾筆，避免洗版

        # 初始化四象限的任務標籤清單
        q1, q2, q3, q4 = [], [], [], []

        for task in self.heap.heap:
            # 有 deadline 的任務：即時重算緊急度，反映目前距離截止日的真實狀況
            # 沒有 deadline：直接使用手動設定的 urgency 值
            current_urgency = task._calculate_urgency() if task.deadline else task.urgency

            is_important = task.importance >= THRESHOLD
            is_urgent    = current_urgency >= THRESHOLD

            # 簡短標籤：ID + 名稱，供矩陣格內顯示
            label = f"[{task.id}] {task.name}"

            if is_important and is_urgent:
                q1.append(label)           # Q1：重要且緊急
            elif is_important and not is_urgent:
                q2.append(label)           # Q2：重要但不緊急
            elif not is_important and is_urgent:
                q3.append(label)           # Q3：不重要但緊急
            else:
                q4.append(label)           # Q4：不重要且不緊急

        def format_cell(tasks, limit=MAX_PER_Q):
            """將任務清單轉為帶項目符號的行列表，超出上限加省略提示"""
            lines = [f"  • {t}" for t in tasks[:limit]]
            if len(tasks) > limit:
                lines.append(f"  ... 另有 {len(tasks) - limit} 筆未顯示")
            if not lines:
                lines.append("  (無任務)")
            return lines

        def display_width(s):
            """計算字串的終端顯示寬度：中文字佔 2 格，ASCII 佔 1 格"""
            return sum(2 if ord(c) > 127 else 1 for c in s)

        def pad(s, width):
            """依顯示寬度補空格，使左右兩欄對齊"""
            return s + " " * max(0, width - display_width(s))

        COL_W = 36  # 每個象限欄的顯示寬度（字元數）

        def render_row(left_lines, right_lines):
            """將左右兩個象限的行列表並排輸出，不足的一側補空白行"""
            max_h = max(len(left_lines), len(right_lines))
            output = []
            for i in range(max_h):
                l = left_lines[i]  if i < len(left_lines)  else ""
                r = right_lines[i] if i < len(right_lines) else ""
                output.append(f"║ {pad(l, COL_W)} ║ {pad(r, COL_W)} ║")
            return output

        H = "═" * (COL_W + 2)
        TOP = f"╔{H}╦{H}╗"
        MID = f"╠{H}╬{H}╣"
        BOT = f"╚{H}╩{H}╝"
        SEP = ["  " + "─" * (COL_W - 2)]  # 象限標題與任務之間的分隔線

        q1_cell = [f"  Q1 重要且緊急  ★  Do First  ({len(q1)} 筆)"]
        q2_cell = [f"  Q2 重要但不緊急  ●  Schedule  ({len(q2)} 筆)"]
        q3_cell = [f"  Q3 不重要但緊急  △  Delegate  ({len(q3)} 筆)"]
        q4_cell = [f"  Q4 不重要且不緊急  ○  Eliminate  ({len(q4)} 筆)"]

        print()
        print(TOP)
        for line in render_row(q1_cell + SEP + format_cell(q1),
                               q2_cell + SEP + format_cell(q2)):
            print(line)
        print(MID)
        for line in render_row(q3_cell + SEP + format_cell(q3),
                               q4_cell + SEP + format_cell(q4)):
            print(line)
        print(BOT)
        print(f"\n閾值：重要度 ≥ {THRESHOLD} 為「重要」，緊急度 ≥ {THRESHOLD} 為「緊急」")

    def do_exit(self, arg):
        """離開系統"""
        self.do_save(arg)
        print("👋 系統關閉，再見！")
        return True

if __name__ == '__main__':
    EisenhowerEngineCLI().cmdloop()