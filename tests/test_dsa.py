from app.utils.dsa import (
    BarcodeHashMap, DuplicateScanDetector, ScanQueue,
    StockPriorityHeap, binary_search, merge_sort,
)


def test_hashmap():
    products = BarcodeHashMap()
    products.insert("8901001", {"name": "Wireless Mouse"})
    assert products.search("8901001")["name"] == "Wireless Mouse"
    assert products.contains("8901001")
    products.delete("8901001")
    assert products.size() == 0


def test_duplicate_detector():
    detector = DuplicateScanDetector()
    assert detector.check_and_add("8901001") is False
    assert detector.check_and_add("8901001") is True


def test_queue_fifo():
    queue = ScanQueue()
    queue.enqueue({"barcode": "1001"})
    queue.enqueue({"barcode": "1002"})
    assert queue.dequeue()["barcode"] == "1001"
    assert queue.dequeue()["barcode"] == "1002"
    assert queue.dequeue() is None


def test_priority_heap():
    heap = StockPriorityHeap()
    heap.add(30, 1)
    heap.add(90, 2)
    heap.add(60, 3)
    assert heap.get_highest_priority() == {"product_id": 2, "risk_score": 90}
    assert heap.get_highest_priority()["product_id"] == 3


def test_binary_search():
    items = [{"sku": "A001"}, {"sku": "A002"}, {"sku": "A003"}]
    assert binary_search(items, "A002")["sku"] == "A002"
    assert binary_search(items, "Z999") is None


def test_merge_sort_descending():
    items = [{"risk_score": 30}, {"risk_score": 90}, {"risk_score": 60}]
    assert [i["risk_score"] for i in merge_sort(items)] == [90, 60, 30]
