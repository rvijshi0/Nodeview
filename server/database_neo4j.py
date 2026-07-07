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
        """Returns empty topology for clean dashboard deployment when Neo4j is unavailable."""
        nodes = []
        edges = []
        return {"nodes": nodes, "edges": edges}

neo4j_store = Neo4jConnector()
