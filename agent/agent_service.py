import os
import socket
import sys
import threading
import time
import datetime
import traceback

# Helper to log startup errors
def log_startup_error(msg):
    if getattr(sys, "frozen", False):
        log_dir = os.path.dirname(sys.executable)
    else:
        try:
            log_dir = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            log_dir = os.getcwd()
    log_path = os.path.join(log_dir, "agent.log")
    try:
        log_line = f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SERVICE-STARTUP] ERROR: {msg}\n"
        print(log_line, end="")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_line)
            f.write(traceback.format_exc() + "\n")
    except Exception as e:
        print(f"Failed to write startup error to agent.log: {e}")

# Try to import win32 modules for Windows Service capability
try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager
    WINDOWS_SERVICE_SUPPORTED = True
except Exception as e:
    WINDOWS_SERVICE_SUPPORTED = False
    log_startup_error(f"Failed to import win32 modules (service support disabled): {e}")

if WINDOWS_SERVICE_SUPPORTED:
    class NodeViewAgentService(win32serviceutil.ServiceFramework):
        _svc_name_ = "NodeViewAgent"
        _svc_display_name_ = "NodeView Distributed Agent"
        _svc_description_ = "Distributed passive network mapping and active segmentation testing visualizer daemon."

        def __init__(self, args):
            try:
                win32serviceutil.ServiceFramework.__init__(self, args)
                self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
                self.agent = None
            except Exception as e:
                log_startup_error(f"Error in Service __init__: {e}")
                raise

        def SvcStop(self):
            try:
                self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
                win32event.SetEvent(self.hWaitStop)
                if self.agent:
                    self.agent.stop()
                servicemanager.LogInfoMsg("NodeViewAgent Service received stop request.")
            except Exception as e:
                log_startup_error(f"Error in SvcStop: {e}")

        def SvcDoRun(self):
            try:
                servicemanager.LogMsg(
                    servicemanager.EVENTLOG_INFORMATION_TYPE,
                    servicemanager.PYS_SERVICE_STARTED,
                    (self._svc_name_, '')
                )
                self.main()
            except Exception as e:
                log_startup_error(f"Error in SvcDoRun: {e}")

        def main(self):
            try:
                # Setup path to import local agent module
                script_dir = os.path.dirname(os.path.abspath(__file__))
                if script_dir not in sys.path:
                    sys.path.append(script_dir)
                
                from agent import NodeViewAgent
                
                # Instantiate agent with default settings (it will load config.json automatically)
                server_url = "http://localhost:8000"
                agent_name = f"Agent-Service-{socket.gethostname()}"
                
                self.agent = NodeViewAgent(server_url=server_url, agent_name=agent_name)
                self.agent.log("Windows Service is starting the agent thread...")
                
                # Start agent logic inside a background daemon thread
                agent_thread = threading.Thread(target=self.agent.start, daemon=True)
                agent_thread.start()
                
                # Wait for SvcStop to be triggered
                while True:
                    # Check status once per second
                    rc = win32event.WaitForSingleObject(self.hWaitStop, 1000)
                    if rc == win32event.WAIT_OBJECT_0:
                        self.agent.log("Windows Service received stop event. Terminating loops.")
                        break
                        
                if self.agent:
                    self.agent.stop()
                
                self.agent.log("Windows Service stopped successfully.")
            except Exception as e:
                log_startup_error(f"Error in Service main loop: {e}")
                if self.agent:
                    self.agent.log(f"Service crashed: {e}", is_error=True)

if __name__ == '__main__':
    # Fallback if pywin32 is not installed or service fails to host
    if not WINDOWS_SERVICE_SUPPORTED:
        print("win32service modules are missing. Starting agent in standard console mode...")
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            if script_dir not in sys.path:
                sys.path.append(script_dir)
            from agent import NodeViewAgent
            agent = NodeViewAgent(server_url="http://localhost:8000", agent_name=f"Agent-Console-{socket.gethostname()}")
            agent.start()
        except Exception as e:
            log_startup_error(f"Console mode fallback crashed: {e}")
            time.sleep(10)
            sys.exit(1)
        sys.exit(0)

    if len(sys.argv) == 1:
        # Executed by the Service Control Manager (SCM) or interactive double-click
        try:
            servicemanager.Initialize()
            servicemanager.PrepareToHostSingle(NodeViewAgentService)
            servicemanager.StartServiceCtrlDispatcher()
        except Exception as e:
            # If start service controller fails (e.g. run directly by user double-clicking it)
            log_startup_error(f"Service dispatcher failed: {e}. Falling back to standard console mode...")
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                if script_dir not in sys.path:
                    sys.path.append(script_dir)
                from agent import NodeViewAgent
                agent = NodeViewAgent(server_url="http://localhost:8000", agent_name=f"Agent-Console-{socket.gethostname()}")
                agent.start()
            except Exception as ex:
                log_startup_error(f"Console fallback crashed: {ex}")
                time.sleep(10)
                sys.exit(1)
            sys.exit(0)
    else:
        # Command line utilities (install, start, stop, remove, etc.)
        try:
            win32serviceutil.HandleCommandLine(NodeViewAgentService)
        except Exception as e:
            log_startup_error(f"Service command line tool failed: {e}")
