from flask import Flask, jsonify, request, render_template
import json
from datetime import datetime
from pathlib import Path
import uuid

app = Flask(__name__, template_folder='templates')

class Task:
    def __init__(self, name, importance, urgency=None, deadline=None, created_at=None, task_id=None):
        self.id = task_id or str(uuid.uuid4())[:6]
        self.name = name
        self.importance = max(1, min(10, float(importance)))
        self.created_at = datetime.fromisoformat(created_at) if created_at else datetime.now()
        self.deadline = datetime.fromisoformat(deadline) if deadline else None
        if self.deadline:
            self.urgency = self._calculate_urgency()
        else:
            self.urgency = max(1, min(10, float(urgency or 1)))

    def _calculate_urgency(self):
        if not self.deadline:
            return 1.0
        now = datetime.now()
        if self.deadline <= now:
            return 10.0
        hours_left = (self.deadline - now).total_seconds() / 3600
        if hours_left >= 336:
            return 1.0
        elif hours_left <= 24:
            return 10.0
        return 10.0 - ((hours_left - 24) * (9.0 / 312))

    def get_score(self):
        if self.deadline:
            self.urgency = self._calculate_urgency()
        base_score = (self.importance * 1.5) + self.urgency
        days_alive = (datetime.now() - self.created_at).total_seconds() / 86400
        return base_score + days_alive * 0.5

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "importance": round(self.importance, 1),
            "urgency": round(self.urgency, 2),
            "deadline": self.deadline.strftime('%Y-%m-%d') if self.deadline else None,
            "created_at": self.created_at.isoformat(),
            "score": round(self.get_score(), 2),
            "has_deadline": self.deadline is not None,
        }


class MaxHeap:
    def __init__(self):
        self.heap = []
        self.pos_map = {}

    def _snapshot(self):
        return [t.to_dict() for t in self.heap]

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
            left, right = 2 * i + 1, 2 * i + 2
            if left < n and self.heap[left].get_score() > self.heap[largest].get_score():
                largest = left
            if right < n and self.heap[right].get_score() > self.heap[largest].get_score():
                largest = right
            if largest != i:
                self._swap(i, largest)
                i = largest
            else:
                break

    def build(self, tasks):
        self.heap = list(tasks)
        n = len(self.heap)
        for i in range(n // 2 - 1, -1, -1):
            self._sift_down(i)
        self.pos_map = {t.id: i for i, t in enumerate(self.heap)}

    def _sift_up_steps(self, i, intro=None):
        steps = []
        steps.append({
            "heap": self._snapshot(), "compare": [i], "swap": [],
            "message": intro or f"節點「{self.heap[i].name}」插入到索引 {i}，開始向上調整 Sift-Up"
        })
        parent = (i - 1) // 2
        while i > 0 and self.heap[i].get_score() > self.heap[parent].get_score():
            cn, cs = self.heap[i].name, self.heap[i].get_score()
            pn, ps = self.heap[parent].name, self.heap[parent].get_score()
            steps.append({
                "heap": self._snapshot(), "compare": [i, parent], "swap": [],
                "message": f"比較：「{cn}」({cs:.1f}) > 父節點「{pn}」({ps:.1f})，需要向上交換"
            })
            pi, pp = i, parent
            self._swap(i, parent)
            steps.append({
                "heap": self._snapshot(), "compare": [], "swap": [pi, pp],
                "message": f"已交換「{cn}」↔「{pn}」，繼續向上檢查"
            })
            i = parent
            parent = (i - 1) // 2
        steps.append({
            "heap": self._snapshot(), "compare": [i], "swap": [],
            "message": "✓ Sift-Up 完成！Heap 最大性質已恢復"
        })
        return steps

    def _sift_down_steps(self, i, intro=None):
        n = len(self.heap)
        if n == 0:
            return []
        steps = []
        steps.append({
            "heap": self._snapshot(), "compare": [i], "swap": [],
            "message": intro or f"從索引 {i} 開始向下調整 Sift-Down"
        })
        while True:
            largest = i
            left, right = 2 * i + 1, 2 * i + 2
            if left < n and self.heap[left].get_score() > self.heap[largest].get_score():
                largest = left
            if right < n and self.heap[right].get_score() > self.heap[largest].get_score():
                largest = right
            if largest != i:
                cn, cs = self.heap[largest].name, self.heap[largest].get_score()
                pn, ps = self.heap[i].name, self.heap[i].get_score()
                cmp = [i] + ([left] if left < n else []) + ([right] if right < n else [])
                steps.append({
                    "heap": self._snapshot(), "compare": cmp, "swap": [],
                    "message": f"子節點最大值「{cn}」({cs:.1f}) > 當前「{pn}」({ps:.1f})，需要向下交換"
                })
                pi, pl = i, largest
                self._swap(i, largest)
                steps.append({
                    "heap": self._snapshot(), "compare": [], "swap": [pi, pl],
                    "message": f"已交換「{pn}」↔「{cn}」，繼續向下檢查"
                })
                i = largest
            else:
                steps.append({
                    "heap": self._snapshot(), "compare": [i], "swap": [],
                    "message": "✓ Sift-Down 完成！Heap 最大性質已恢復"
                })
                break
        return steps

    def insert(self, task):
        self.heap.append(task)
        idx = len(self.heap) - 1
        self.pos_map[task.id] = idx
        return self._sift_up_steps(idx)

    def extract_max(self):
        if not self.heap:
            return None, []
        max_task = self.heap[0]
        last = self.heap.pop()
        del self.pos_map[max_task.id]
        if not self.heap:
            return max_task, [{"heap": [], "compare": [], "swap": [], "message": f"移除「{max_task.name}」，Heap 已清空"}]
        self.heap[0] = last
        self.pos_map[last.id] = 0
        intro = f"提取根節點「{max_task.name}」，將末端節點「{last.name}」移至根部，開始 Sift-Down"
        return max_task, self._sift_down_steps(0, intro)

    def remove_by_id(self, task_id):
        idx = self.pos_map.get(task_id)
        if idx is None:
            return None, []
        removed = self.heap[idx]
        last_idx = len(self.heap) - 1
        if idx == last_idx:
            self.heap.pop()
            del self.pos_map[removed.id]
            return removed, [{"heap": self._snapshot(), "compare": [], "swap": [],
                               "message": f"移除末端節點「{removed.name}」"}]
        last = self.heap.pop()
        del self.pos_map[removed.id]
        self.heap[idx] = last
        self.pos_map[last.id] = idx
        parent = (idx - 1) // 2
        steps = [{"heap": self._snapshot(), "compare": [idx], "swap": [],
                  "message": f"移除「{removed.name}」，以末端節點「{last.name}」填補位置 {idx}"}]
        if idx > 0 and self.heap[idx].get_score() > self.heap[parent].get_score():
            steps.extend(self._sift_up_steps(idx,
                f"「{last.name}」({self.heap[idx].get_score():.1f}) > 父節點「{self.heap[parent].name}」({self.heap[parent].get_score():.1f})，需要 Sift-Up"))
        else:
            steps.extend(self._sift_down_steps(idx, f"「{last.name}」需要向下調整，進行 Sift-Down"))
        return removed, steps

    def refresh(self):
        n = len(self.heap)
        for i in range(n // 2 - 1, -1, -1):
            self._sift_down(i)
        self.pos_map = {t.id: i for i, t in enumerate(self.heap)}

    def peek_max(self):
        return self.heap[0] if self.heap else None

    def snapshot(self):
        return self._snapshot()


heap = MaxHeap()
current_task_id = [None]
DATA_FILE = Path(__file__).with_name('tasks_data.json')


def startup_load():
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        tasks = []
        for d in data:
            t = Task(
                name=d['name'], importance=d['importance'],
                urgency=d['urgency'],
                deadline=d['deadline'][:10] if d['deadline'] else None,
                created_at=d['created_at'], task_id=d['id']
            )
            tasks.append(t)
        heap.build(tasks)
        print(f"✓ 已載入 {len(tasks)} 筆任務")
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"載入失敗：{e}")


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    heap.refresh()
    sorted_tasks = sorted(heap.heap, key=lambda x: x.get_score(), reverse=True)
    return jsonify({"tasks": [t.to_dict() for t in sorted_tasks], "heap": heap.snapshot()})


@app.route('/api/tasks', methods=['POST'])
def add_task():
    data = request.json or {}
    name = data.get('name', '').strip()
    importance = data.get('importance')
    urgency = data.get('urgency')
    deadline = data.get('deadline')

    if not name or importance is None:
        return jsonify({"error": "缺少必要欄位"}), 400

    try:
        if deadline:
            task = Task(name=name, importance=float(importance), deadline=deadline)
        else:
            task = Task(name=name, importance=float(importance), urgency=float(urgency or 1))
        steps = heap.insert(task)
        return jsonify({"success": True, "task": task.to_dict(), "steps": steps})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/tasks/next', methods=['GET'])
def next_task():
    heap.refresh()
    task = heap.peek_max()
    if not task:
        current_task_id[0] = None
        return jsonify({"task": None, "heap": [], "message": "目前無待辦任務 🎉"})
    current_task_id[0] = task.id
    return jsonify({
        "task": task.to_dict(),
        "heap": heap.snapshot(),
        "highlight": [0],
        "message": f"最高優先：{task.name}（權重 {task.get_score():.2f}）"
    })


@app.route('/api/tasks/done', methods=['POST'])
def done_task():
    if not heap.heap:
        current_task_id[0] = None
        return jsonify({"success": False, "message": "目前無待辦任務"})
    if not current_task_id[0]:
        return jsonify({"success": False, "message": "請先點擊「下一個任務」"})
    removed, steps = heap.remove_by_id(current_task_id[0])
    if not removed:
        current_task_id[0] = None
        return jsonify({"success": False, "message": "任務不存在"})
    current_task_id[0] = None
    return jsonify({"success": True, "task": removed.to_dict(), "steps": steps})


@app.route('/api/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    removed, steps = heap.remove_by_id(task_id)
    if not removed:
        return jsonify({"error": "任務不存在"}), 404
    if current_task_id[0] == task_id:
        current_task_id[0] = None
    return jsonify({"success": True, "task": removed.to_dict(), "steps": steps})


@app.route('/api/save', methods=['POST'])
def save_tasks():
    data = []
    for t in heap.heap:
        d = t.to_dict()
        d.pop('score', None)
        d.pop('has_deadline', None)
        data.append(d)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return jsonify({"success": True, "count": len(data)})


@app.route('/api/load', methods=['POST'])
def load_tasks():
    global heap
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        tasks = []
        for d in data:
            t = Task(
                name=d['name'], importance=d['importance'],
                urgency=d['urgency'],
                deadline=d['deadline'][:10] if d['deadline'] else None,
                created_at=d['created_at'], task_id=d['id']
            )
            tasks.append(t)
        heap = MaxHeap()
        heap.build(tasks)
        current_task_id[0] = None
        return jsonify({"success": True, "count": len(tasks)})
    except FileNotFoundError:
        return jsonify({"error": "找不到存檔檔案"}), 404


if __name__ == '__main__':
    startup_load()
    print("啟動伺服器：http://127.0.0.1:5001")
    app.run(debug=True, port=5001)
