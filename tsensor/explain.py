import sys
import traceback

from tsensor.parse import *

class dbg:
    def __init__(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if exc_type is not None:
            if not self.is_interesting_exception(exc_value):
                return
            # print("exception:", exc_value, exc_traceback)
            # traceback.print_tb(exc_traceback, limit=5, file=sys.stdout)
            exc_frame = self.deepest_frame(exc_traceback)
            module, name, filename, line, code = self.info(exc_frame)
            # print('info', module, name, filename, line, code)
            if code is not None:
                # could be internal like "__array_function__ internals" in numpy
                self.process_exception(code, exc_frame, exc_value)

    def process_exception(self, code, exc_frame, exc_value):
        augment = ""
        try:
            p = PyExprParser(code)
            t = p.parse()
            try:
                t.eval(exc_frame)
            except IncrEvalTrap as exc:
                subexpr = exc.offending_expr
                # print("trap evaluating:\n", repr(subexpr), "\nin", repr(t))
                explanation = subexpr.explain()
                if explanation is not None:
                    augment = explanation
        except BaseException as e:
            print(f"exception while eval({code})", e)
            traceback.print_tb(e.__traceback__, limit=5, file=sys.stdout)
        # Reuse exception but overwrite the message
        exc_value.args = [exc_value.args[0] + "\n" + augment]

    def is_interesting_exception(self, e):
        sentinels = {'matmul', 'THTensorMath', 'tensor', 'tensors', 'dimension',
                     'not aligned', 'size mismatch', 'shape', 'shapes'}
        msg = e.args[0]
        return sum([s in msg for s in sentinels])>0

    def deepest_frame(self, exc_traceback):
        tb = exc_traceback
        # don't trace into internals of numpy etc... with filenames like '<__array_function__ internals>'
        while tb.tb_next != None and not tb.tb_next.tb_frame.f_code.co_filename.startswith('<'):
            tb = tb.tb_next
        return tb.tb_frame

    def info(self, frame):
        if hasattr(frame, '__name__'):
            module = frame.f_globals['__name__']
        else:
            module = None
        info = inspect.getframeinfo(frame)
        if info.code_context is not None:
            code = info.code_context[0].strip()
        else:
            code = None
        filename, line = info.filename, info.lineno
        name = info.function
        return module, name, filename, line, code

class Tracer:
    def __init__(self, modules=['__main__'], filenames=[]):
        self.modules = modules
        self.filenames = filenames
        self.exceptions = set()

    def listener(self, frame, event, arg):
        module = frame.f_globals['__name__']
        if module not in self.modules:
            return

        info = inspect.getframeinfo(frame)
        filename, line = info.filename, info.lineno
        name = info.function
        if len(self.filenames)>0 and filename not in self.filenames:
            return

        if event=='call':
            self.call_listener(module, name, filename, line)
            return self.listener

        # TODO: ignore c_call etc...

        if event=='line':
            self.line_listener(module, name, filename, line, info)

        return None

    def call_listener(self, module, name, filename, line):
        # print(f"A call encountered in {module}.{name}() at {filename}:{line}")
        pass

    def line_listener(self, module, name, filename, line, info):
        code = info.code_context[0].strip()
        if code.startswith("sys.settrace(None)"):
            return
        p = PyExprParser(code)
        t = p.parse()
        if t is not None:
            print(f"A line encountered in {module}.{name}() at {filename}:{line}")
            print("\t", code)
            print("\t", repr(t))


class explain:
    def __enter__(self):
        print("ON trace")
        tr = Tracer()
        sys.settrace(tr.listener)
        frame = sys._getframe()
        prev = frame.f_back # get block wrapped in "with"
        # if frame.f_back is None:
        # prev = stack()[2]
        prev.f_trace = tr.listener

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.settrace(None)
        print("OFF trace")


def _shape(v):
    if hasattr(v, "shape"):
        if isinstance(v.shape, torch.Size):
            if len(v.shape)==0:
                return None
            return list(v.shape)
        return v.shape
    return None