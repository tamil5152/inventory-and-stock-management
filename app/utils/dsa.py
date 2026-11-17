
import heapq
from collections import deque


# =====================================================
# 1. HASHMAP - BARCODE LOOKUP
# =====================================================

class BarcodeHashMap:

    def __init__(self):
        self.products = {}

    def insert(self, barcode, product):

        if not barcode:
            raise ValueError("Barcode cannot be empty.")

        self.products[barcode] = product

    def search(self, barcode):

        return self.products.get(barcode)

    def delete(self, barcode):

        self.products.pop(barcode, None)

    def contains(self, barcode):

        return barcode in self.products

    def size(self):

        return len(self.products)


# =====================================================
# 2. HASHSET - DUPLICATE SCAN DETECTION
# =====================================================

class DuplicateScanDetector:

    def __init__(self):
        self.scanned = set()

    def check_and_add(self, barcode):

        if barcode in self.scanned:
            return True

        self.scanned.add(barcode)

        return False

    def remove(self, barcode):

        self.scanned.discard(barcode)

    def reset(self):

        self.scanned.clear()

    def count(self):

        return len(self.scanned)


# =====================================================
# 3. QUEUE - SCAN PROCESSING
# =====================================================

class ScanQueue:

    def __init__(self):
        self.queue = deque()

    def enqueue(self, scan_data):

        self.queue.append(scan_data)

    def dequeue(self):

        if not self.queue:
            return None

        return self.queue.popleft()

    def peek(self):

        if not self.queue:
            return None

        return self.queue[0]

    def is_empty(self):

        return len(self.queue) == 0

    def size(self):

        return len(self.queue)


# =====================================================
# 4. MIN HEAP - STOCK RISK PRIORITIZATION
# =====================================================

class StockPriorityHeap:

    def __init__(self):
        self.heap = []

    def add(self, risk_score, product_id):

        if not 0 <= risk_score <= 100:
            raise ValueError("Risk score must be between 0 and 100.")

        # Negative score makes highest risk come out first.
        heapq.heappush(
            self.heap,
            (-risk_score, product_id)
        )

    def get_highest_priority(self):

        if not self.heap:
            return None

        risk_score, product_id = heapq.heappop(
            self.heap
        )

        return {
            "product_id": product_id,
            "risk_score": -risk_score
        }

    def get_all(self):

        return [
            {
                "product_id": product_id,
                "risk_score": -risk_score
            }
            for risk_score, product_id in sorted(self.heap)
        ]

    def size(self):

        return len(self.heap)


# =====================================================
# 5. BINARY SEARCH - PRODUCT SKU SEARCH
# =====================================================

def binary_search(sorted_products, target_sku):

    left = 0
    right = len(sorted_products) - 1

    while left <= right:

        mid = (left + right) // 2

        current_sku = sorted_products[mid]["sku"]

        if current_sku == target_sku:
            return sorted_products[mid]

        elif current_sku < target_sku:
            left = mid + 1

        else:
            right = mid - 1

    return None


# =====================================================
# 6. MERGE SORT - PRODUCT RISK SORTING
# =====================================================

def merge_sort(products, key="risk_score"):

    if len(products) <= 1:
        return products

    middle = len(products) // 2

    left = merge_sort(products[:middle], key)

    right = merge_sort(products[middle:], key)

    return merge(left, right, key)


def merge(left, right, key):

    result = []

    i = 0
    j = 0

    while i < len(left) and j < len(right):

        if left[i][key] >= right[j][key]:

            result.append(left[i])
            i += 1

        else:

            result.append(right[j])
            j += 1

    result.extend(left[i:])
    result.extend(right[j:])

    return result
