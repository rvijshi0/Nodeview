try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    print("[Neo4j] neo4j package not installed. Using mock topology fallback.")

import os

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"  # Default credentials matching docker configuration

class Neo4jConnector:
    def __init__(self):
        self.driver = None
        if not NEO4J_AVAILABLE:
            return
        try:
            self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        except Exception as e:
            print(f"Neo4j connector init warning: {e}. Using mock topology fallback.")

    def close(self):
        if self.driver:
            self.driver.close()

    def merge_agent_node(self, name, ip, mac):
        """Merges an active monitoring agent into the topology graph."""
        if not self.driver:
            return
        query = """
        MERGE (a:Agent {mac: $mac})
        ON CREATE SET a.name = $name, a.ip = $ip, a.type = 'agent', a.last_seen = timestamp()
        ON MATCH SET a.name = $name, a.ip = $ip, a.last_seen = timestamp()
        RETURN a
        """
        try:
            with self.driver.session() as session:
                session.run(query, name=name, ip=ip, mac=mac)
        except Exception as e:
            print(f"[Neo4j] merge_agent_node failed: {e}. Disabling Neo4j driver.")
            self.driver = None

    def merge_peripheral_device(self, ip, mac, label, device_type, agent_mac):
        """Merges a discovered peripheral node and links it to the discovering agent."""
        if not self.driver:
            return
        # Merge device
        query_dev = """
        MERGE (d:Device {mac: $mac})
        ON CREATE SET d.ip = $ip, d.label = $label, d.type = $device_type, d.last_seen = timestamp()
        ON MATCH SET d.ip = $ip, d.label = $label, d.last_seen = timestamp()
        """
        # Connect device to agent
        query_rel = """
        MATCH (a:Agent {mac: $agent_mac})
        MATCH (d:Device {mac: $mac})
        MERGE (d)-[r:DISCOVERED_BY]->(a)
        SET r.last_seen = timestamp()
        """
        try:
            with self.driver.session() as session:
                session.run(query_dev, mac=mac, ip=ip, label=label, device_type=device_type)
                session.run(query_rel, agent_mac=agent_mac, mac=mac)
        except Exception as e:
            print(f"[Neo4j] merge_peripheral_device failed: {e}. Disabling Neo4j driver.")
            self.driver = None

    def merge_network_link(self, src_mac, dst_mac, link_type="CONNECTED_TO"):
        """Establishes topological edge maps between two nodes."""
        if not self.driver:
            return
        query = f"""
        MATCH (n1) WHERE n1.mac = $src_mac
        MATCH (n2) WHERE n2.mac = $dst_mac
        MERGE (n1)-[r:{{link_type}}]->(n2)
        SET r.last_seen = timestamp()
        """
        try:
            with self.driver.session() as session:
                session.run(query, src_mac=src_mac, dst_mac=dst_mac)
        except Exception as e:
            print(f"[Neo4j] merge_network_link failed: {e}. Disabling Neo4j driver.")
            self.driver = None

    def get_topology_data(self):
        """
        Queries all nodes and relationships to format them for React cytoscape UI consumption.
        """
        if not self.driver:
            # Fallback mock representation for local standalone verification
            return self.get_mock_fallback_topology()
            
        nodes = []
        edges = []
        
        query_nodes = "MATCH (n) RETURN id(n) as id, labels(n) as labels, properties(n) as props"
        query_edges = "MATCH (n1)-[r]->(n2) RETURN id(r) as id, id(n1) as source, id(n2) as target, type(r) as type"
        
        with self.driver.session() as session:
            result_nodes = session.run(query_nodes)
            for record in result_nodes:
                node_id = str(record["id"])
                props = record["props"]
                labels = record["labels"]
                nodes.append({
                    "data": {
                        "id": node_id,
                        "label": props.get("label", props.get("name", "Unknown")),
                        "type": props.get("type", labels[0].lower() if labels else "device"),
                        "ip": props.get("ip", ""),
                        "mac": props.get("mac", ""),
                        "last_seen": props.get("last_seen", "")
                    }
                })
                
            result_edges = session.run(query_edges)
            for record in result_edges:
                edges.append({
                    "data": {
                        "id": str(record["id"]),
                        "source": str(record["source"]),
                        "target": str(record["target"]),
                        "type": record["type"]
                    }
                })
                
        return {"nodes": nodes, "edges": edges}

    def get_mock_fallback_topology(self):
        """Simulates full mock topology for client demonstrations when bolt endpoint is unavailable."""
        nodes = [
            {"data": {"id": "fw", "label": "Enterprise Firewall", "type": "firewall", "ip": "10.0.1.1", "mac": "00:0c:29:11:22:33"}},
            {"data": {"id": "sw1", "label": "Switch (VLAN 10)", "type": "switch", "ip": "10.0.10.1", "mac": "00:01:42:aa:bb:cc"}},
            {"data": {"id": "wlc", "label": "Wireless Controller", "type": "wlc", "ip": "10.0.10.2", "mac": "00:15:5d:99:88:77"}},
            {"data": {"id": "ap1", "label": "Access Point East", "type": "ap", "ip": "10.0.10.5", "mac": "fc:ec:da:00:11:22"}},
            {"data": {"id": "ag1", "label": "Agent-East", "type": "agent", "ip": "10.0.10.15", "mac": "00:50:56:88:99:aa"}},
            {"data": {"id": "ag2", "label": "Agent-West", "type": "agent", "ip": "10.0.10.16", "mac": "00:50:56:88:99:bb"}},
            # Connected to AP (VLAN 10) - 7 devices to trigger React auto-grouping limit (>5 nodes)
            {"data": {"id": "lap1", "label": "Laptop-John", "type": "laptop", "ip": "10.0.10.51", "mac": "00:1a:e8:11:22:33"}},
            {"data": {"id": "lap2", "label": "Laptop-Mary", "type": "laptop", "ip": "10.0.10.52", "mac": "00:1a:e8:11:22:44"}},
            {"data": {"id": "lap3", "label": "Laptop-Dev", "type": "laptop", "ip": "10.0.10.53", "mac": "00:1a:e8:11:22:55"}},
            {"data": {"id": "lap4", "label": "Laptop-QA", "type": "laptop", "ip": "10.0.10.54", "mac": "00:1a:e8:11:22:66"}},
            {"data": {"id": "lap5", "label": "Laptop-Sales", "type": "laptop", "ip": "10.0.10.55", "mac": "00:1a:e8:11:22:77"}},
            {"data": {"id": "lap6", "label": "Laptop-HR", "type": "laptop", "ip": "10.0.10.56", "mac": "00:1a:e8:11:22:88"}},
            {"data": {"id": "lap7", "label": "Laptop-Fin", "type": "laptop", "ip": "10.0.10.57", "mac": "00:1a:e8:11:22:99"}},
            
            # Mobile devices connected to AP
            {"data": {"id": "mob1", "label": "iPhone-Admin", "type": "mobile", "ip": "10.0.10.80", "mac": "d8:d3:85:ff:ee:dd"}},
            {"data": {"id": "mob2", "label": "Android-Guest", "type": "mobile", "ip": "10.0.10.81", "mac": "e0:d9:e3:12:34:56"}},
        ]
        
        edges = [
            {"data": {"id": "fw-sw1", "source": "fw", "target": "sw1", "type": "CONNECTED_TO"}},
            {"data": {"id": "sw1-wlc", "source": "sw1", "target": "wlc", "type": "CONNECTED_TO"}},
            {"data": {"id": "sw1-ap1", "source": "sw1", "target": "ap1", "type": "CONNECTED_TO"}},
            {"data": {"id": "sw1-ag1", "source": "sw1", "target": "ag1", "type": "CONNECTED_TO"}},
            {"data": {"id": "sw1-ag2", "source": "sw1", "target": "ag2", "type": "CONNECTED_TO"}},
            # Device mappings to AP
            {"data": {"id": "ap1-lap1", "source": "ap1", "target": "lap1", "type": "CONNECTED_TO"}},
            {"data": {"id": "ap1-lap2", "source": "ap1", "target": "lap2", "type": "CONNECTED_TO"}},
            {"data": {"id": "ap1-lap3", "source": "ap1", "target": "lap3", "type": "CONNECTED_TO"}},
            {"data": {"id": "ap1-lap4", "source": "ap1", "target": "lap4", "type": "CONNECTED_TO"}},
            {"data": {"id": "ap1-lap5", "source": "ap1", "target": "lap5", "type": "CONNECTED_TO"}},
            {"data": {"id": "ap1-lap6", "source": "ap1", "target": "lap6", "type": "CONNECTED_TO"}},
            {"data": {"id": "ap1-lap7", "source": "ap1", "target": "lap7", "type": "CONNECTED_TO"}},
            
            {"data": {"id": "ap1-mob1", "source": "ap1", "target": "mob1", "type": "CONNECTED_TO"}},
            {"data": {"id": "ap1-mob2", "source": "ap1", "target": "mob2", "type": "CONNECTED_TO"}},
        ]
        return {"nodes": nodes, "edges": edges}

neo4j_store = Neo4jConnector()
