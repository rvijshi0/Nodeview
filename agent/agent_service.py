import os
import socket
import sys
import threading
import time

# Try to import win32 modules for Windows Service capability
try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager
    WINDOWS_SERVICE_SUPPORTED = True
except ImportError:
    WINDOWS_SERVICE_SUPPORTED = False

if WINDOWS_SERVICE_SUPPORTED:
    class NodeViewAgentService(win32serviceutil.ServiceFramework):
        _svc_name_ = "NodeViewAgent"
        _svc_display_name_ = "NodeView Distributed Agent"
        _svc_description_ = "Distributed passive network mapping and active segmentation testing visualizer daemon."

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
            self.agent = None

        def SvcStop(self):
            # Signal the stop event
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self.hWaitStop)
            if self.agent:
                self.agent.stop()
            servicemanager.LogInfoMsg("NodeViewAgent Service received stop request.")

        def SvcDoRun(self):
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, '')
            )
            self.main()

        def main(self):
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

if __name__ == '__main__':
    if not WINDOWS_SERVICE_SUPPORTED:
        print("CRITICAL: win32service modules are missing. Please install pywin32 library: pip install pywin32")
        sys.exit(1)
        
    if len(sys.argv) == 1:
        # Executed by the Service Control Manager (SCM)
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(NodeViewAgentService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        # Command line utilities (install, start, stop, remove, etc.)
        win32serviceutil.HandleCommandLine(NodeViewAgentService)
