class MusicQueue:
    def __init__(self):
        # Each entry: (url, title, ctx, duration, requester, search_query) where url/title/duration may be None for pending
        self.queues = {}  # guild_id: list
        self.now_playing = {}  # guild_id: (url, title, ctx, duration, requester, search_query)

    def add(self, guild_id, url_or_query, title, ctx, duration, requester, pending=False):
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        if pending:
            self.queues[guild_id].append((None, None, ctx, None, requester, url_or_query))
        else:
            self.queues[guild_id].append((url_or_query, title, ctx, duration, requester, url_or_query))

    def next(self, guild_id):
        if guild_id in self.queues and self.queues[guild_id]:
            next_track = self.queues[guild_id].pop(0)
            self.now_playing[guild_id] = next_track
            return next_track
        else:
            self.now_playing[guild_id] = None
            return None

    def set_now_playing(self, guild_id, url, title, ctx, duration, requester, search_query=None):
        self.now_playing[guild_id] = (url, title, ctx, duration, requester, search_query or url)

    def clear(self, guild_id):
        self.queues[guild_id] = []
        self.now_playing[guild_id] = None

    def is_empty(self):
        return all(not q for q in self.queues.values())

    def get_queue(self, guild_id):
        return self.queues.get(guild_id, [])

    def get_now_playing(self, guild_id):
        return self.now_playing.get(guild_id)

    def mark_resolved(self, guild_id, idx, url, title, duration):
        q = self.queues[guild_id]
        _, _, ctx, _, requester, search_query = q[idx]
        q[idx] = (url, title, ctx, duration, requester, search_query)

    def next_pending(self, guild_id):
        q = self.queues.get(guild_id, [])
        for idx, (url, title, ctx, duration, requester, search_query) in enumerate(q):
            if title is None:
                return idx, search_query, ctx, requester
        return None 