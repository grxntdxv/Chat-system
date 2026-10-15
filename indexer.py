import pickle
import string


class Index:
    def __init__(self, name):
        self.name = name
        self.msgs = []
        self.index = {}
        self.total_msgs = 0
        self.total_words = 0

    def normalize(self, word):
        return word.lower().strip(string.punctuation)

    def get_total_words(self):
        return self.total_words

    def get_msg_size(self):
        return self.total_msgs

    def get_msg(self, n):
        return self.msgs[n]

    def add_msg(self, m):
        self.msgs.append(m)
        self.total_msgs += 1

    def add_msg_and_index(self, m):
        self.add_msg(m)
        self.indexing(m, self.total_msgs - 1)

    def indexing(self, m, l):
        words = m.split()
        self.total_words += len(words)
        for wd in words:
            norm = self.normalize(wd)
            if norm:
                self.index.setdefault(norm, []).append(l)

    def search(self, term):
        term = self.normalize(term)
        if term in self.index:
            return [(i, self.msgs[i]) for i in self.index[term]]
        return []


class PIndex(Index):
    def __init__(self, name):
        super().__init__(name)
        with open("roman.txt.pk", "rb") as f:
            self.int2roman = pickle.load(f)
        self.load_poems()

    def load_poems(self):
        with open(self.name, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                self.add_msg_and_index(line.rstrip())

    def get_poem(self, p):
        p_str = self.int2roman[p] + "."
        p_next = self.int2roman[p + 1] + "."

        start_line = -1
        for i in range(self.get_msg_size()):
            if self.get_msg(i) == p_str:
                start_line = i
                break
        if start_line == -1:
            return []

        poem = []
        for i in range(start_line + 1, self.get_msg_size()):
            line = self.get_msg(i)
            if line == p_next:
                break
            poem.append(line)
        return poem