"""Windows job ownership ensures PyInstaller's child also dies on cancellation."""
from __future__ import annotations

import subprocess
import sys
import threading


class WindowsJob:
    def __init__(self, process):
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                        ("flags", wintypes.DWORD), ("minimum", ctypes.c_size_t),
                        ("maximum", ctypes.c_size_t), ("processes", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                        ("scheduling", wintypes.DWORD)]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in
                        ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("basic", BasicLimits), ("io", IoCounters),
                        ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                        ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel, self._lock = kernel, threading.Lock()
        self._handle = kernel.CreateJobObjectW(None, None)
        if not self._handle:
            raise OSError("Cannot own worker job")
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(self._handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(self._handle, int(process._handle)):
            self.close()
            raise OSError("Cannot assign worker job")
        native = ctypes.WinDLL("ntdll")
        native.NtResumeProcess.argtypes = [wintypes.HANDLE]
        native.NtResumeProcess.restype = ctypes.c_long
        if native.NtResumeProcess(int(process._handle)) != 0:
            self.close()
            raise OSError("Cannot resume worker")

    def close(self):
        with self._lock:
            if self._handle:
                self._kernel.CloseHandle(self._handle)
                self._handle = None


def start_process(command, environment):
    flags = (subprocess.CREATE_NO_WINDOW | 0x4) if sys.platform == "win32" else 0
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, encoding="utf-8", env=environment,
                               creationflags=flags)
    try:
        process.worker_job = WindowsJob(process) if sys.platform == "win32" else None
    except OSError:
        process.kill()
        process.wait()
        process.stdin.close()
        process.stdout.close()
        raise
    return process


def stop_process(process):
    if process.worker_job:
        process.worker_job.close()
    elif process.poll() is None:
        process.kill()
