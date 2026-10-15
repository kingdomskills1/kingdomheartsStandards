

class ViewerHistoryMixin:

    def _snapshot_state(self):
        if self.original_image is None:
            return None

        return (
            self.original_image.copy(),
            self.rotation,
            self.zoom,
            self.fit_mode,
            self.pan_x,
            self.pan_y,
            self.image_path,
        )

    def _record_history(self):
        state = self._snapshot_state()
        if state is None:
            return

        if self.undo_stack and self.undo_stack[-1] == state:
            return

        self.undo_stack.append(state)
        if len(self.undo_stack) > self.history_limit:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def _restore_state(self, state):
        if state is None:
            return

        original_image, rotation, zoom, fit_mode, pan_x, pan_y, image_path = state
        self.original_image = original_image.copy()
        self.rotation = rotation
        self.zoom = zoom
        self.fit_mode = fit_mode
        self.pan_x = pan_x
        self.pan_y = pan_y
        self.image_path = image_path
        self.display_current_image()

    def undo(self):
        if not self.undo_stack or self.original_image is None:
            return

        current = self._snapshot_state()
        self.redo_stack.append(current)
        previous = self.undo_stack.pop()
        self._restore_state(previous)

    def redo(self):
        if not self.redo_stack:
            return

        current = self._snapshot_state()
        self.undo_stack.append(current)
        next_state = self.redo_stack.pop()
        self._restore_state(next_state)
