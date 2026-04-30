/**
 * FractalClaw Monitor - Canvas-based Fractal Tree Visualization
 */

class FractalTreeVisualizer {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.agents = new Map();
        this.rootAgent = null;
        this.animationId = null;
        this.pulsePhase = 0;

        this.resize();
        window.addEventListener('resize', () => this.resize());

        this.symbols = {
            root: '◈',
            coordinator: '◇',
            worker: '●',
            specialist: '◆',
            idle: '○',
            planning: '◐',
            thinking: '◑',
            executing: '◉',
            delegating: '◎',
            error: '✕',
            stopped: '⊘',
        };

        this.colors = {
            root: '#c792ea',
            coordinator: '#82aaff',
            specialist: '#ffcb6b',
            worker: '#c3e88d',
            idle: '#676e95',
            planning: '#ffcb6b',
            thinking: '#82aaff',
            executing: '#c3e88d',
            delegating: '#c792ea',
            error: '#ff5372',
            stopped: '#676e95',
            line: '#2a2a4a',
            lineActive: '#82aaff',
        };

        this.startAnimation();
    }

    resize() {
        const parent = this.canvas.parentElement;
        this.canvas.width = parent.clientWidth;
        this.canvas.height = parent.clientHeight;
        this.draw();
    }

    addAgent(agentData) {
        this.agents.set(agentData.id, {
            ...agentData,
            x: 0,
            y: 0,
            targetX: 0,
            targetY: 0,
            pulseIntensity: 0,
        });
        this.updateHierarchy();
    }

    updateAgentState(agentId, state) {
        const agent = this.agents.get(agentId);
        if (agent) {
            agent.state = state;
            if (state === 'executing' || state === 'delegating') {
                agent.pulseIntensity = 1;
            }
        }
    }

    updateHierarchy() {
        // Find root
        this.rootAgent = null;
        for (const agent of this.agents.values()) {
            if (!agent.parent_id) {
                this.rootAgent = agent;
                break;
            }
        }

        // Build children lists
        for (const agent of this.agents.values()) {
            agent.children = [];
        }
        for (const agent of this.agents.values()) {
            if (agent.parent_id && this.agents.has(agent.parent_id)) {
                this.agents.get(agent.parent_id).children.push(agent);
            }
        }
    }

    calculateLayout() {
        if (!this.rootAgent) return;

        const width = this.canvas.width;
        const height = this.canvas.height;
        const levelHeight = Math.min(height / 6, 80);
        const nodeRadius = 25;

        const layoutNode = (node, level, startX, endX) => {
            const x = (startX + endX) / 2;
            const y = 60 + level * levelHeight;

            node.targetX = x;
            node.targetY = y;

            if (node.children && node.children.length > 0) {
                const childWidth = (endX - startX) / node.children.length;
                node.children.forEach((child, i) => {
                    layoutNode(child, level + 1, startX + i * childWidth, startX + (i + 1) * childWidth);
                });
            }
        };

        layoutNode(this.rootAgent, 0, nodeRadius, width - nodeRadius);

        // Smooth transition
        for (const agent of this.agents.values()) {
            if (agent.x === 0) {
                agent.x = agent.targetX;
                agent.y = agent.targetY;
            } else {
                agent.x += (agent.targetX - agent.x) * 0.1;
                agent.y += (agent.targetY - agent.y) * 0.1;
            }
        }
    }

    drawFractalBackground() {
        const ctx = this.ctx;
        const w = this.canvas.width;
        const h = this.canvas.height;

        // Draw subtle fractal pattern
        ctx.save();
        ctx.globalAlpha = 0.03;
        ctx.strokeStyle = '#c792ea';
        ctx.lineWidth = 1;

        const drawBranch = (x, y, angle, length, depth) => {
            if (depth <= 0 || length < 2) return;

            const endX = x + Math.cos(angle) * length;
            const endY = y + Math.sin(angle) * length;

            ctx.beginPath();
            ctx.moveTo(x, y);
            ctx.lineTo(endX, endY);
            ctx.stroke();

            const newLength = length * 0.7;
            drawBranch(endX, endY, angle - 0.5, newLength, depth - 1);
            drawBranch(endX, endY, angle + 0.5, newLength, depth - 1);
        };

        // Draw a few fractal trees in background
        drawBranch(w * 0.2, h, -Math.PI / 2, 60, 5);
        drawBranch(w * 0.8, h, -Math.PI / 2, 60, 5);

        ctx.restore();
    }

    drawConnection(parent, child) {
        const ctx = this.ctx;

        ctx.beginPath();
        ctx.moveTo(parent.x, parent.y);

        // Curved connection
        const midY = (parent.y + child.y) / 2;
        ctx.bezierCurveTo(
            parent.x, midY,
            child.x, midY,
            child.x, child.y
        );

        // Active connections pulse
        const isActive = child.state === 'executing' || child.state === 'delegating';
        ctx.strokeStyle = isActive ? this.colors.lineActive : this.colors.line;
        ctx.lineWidth = isActive ? 2 : 1;
        ctx.globalAlpha = isActive ? 0.6 + Math.sin(this.pulsePhase * 3) * 0.2 : 0.3;
        ctx.stroke();
        ctx.globalAlpha = 1;

        // Draw data flow animation on active connections
        if (isActive) {
            const t = (this.pulsePhase % 1);
            const flowX = parent.x + (child.x - parent.x) * t;
            const flowY = parent.y + (child.y - parent.y) * t;

            ctx.beginPath();
            ctx.arc(flowX, flowY, 3, 0, Math.PI * 2);
            ctx.fillStyle = this.colors.lineActive;
            ctx.fill();
        }
    }

    drawNode(agent) {
        const ctx = this.ctx;
        const x = agent.x;
        const y = agent.y;
        const role = agent.role || 'worker';
        const state = agent.state || 'idle';

        // Determine symbol and color
        let symbol;
        if (role === 'root') symbol = this.symbols.root;
        else if (role === 'coordinator') symbol = this.symbols.coordinator;
        else if (role === 'specialist') symbol = this.symbols.specialist;
        else if (state === 'executing') symbol = this.symbols.executing;
        else if (state === 'delegating') symbol = this.symbols.delegating;
        else if (state === 'planning') symbol = this.symbols.planning;
        else if (state === 'thinking') symbol = this.symbols.thinking;
        else if (state === 'error') symbol = this.symbols.error;
        else if (state === 'stopped') symbol = this.symbols.stopped;
        else symbol = this.symbols.idle;

        const color = this.colors[state] || this.colors[role] || this.colors.idle;

        // Draw pulse effect for active agents
        if (state === 'executing' || state === 'delegating') {
            const pulseRadius = 30 + Math.sin(this.pulsePhase * 2) * 5;
            ctx.beginPath();
            ctx.arc(x, y, pulseRadius, 0, Math.PI * 2);
            ctx.fillStyle = color;
            ctx.globalAlpha = 0.1 + Math.sin(this.pulsePhase * 2) * 0.05;
            ctx.fill();
            ctx.globalAlpha = 1;
        }

        // Draw node circle background
        ctx.beginPath();
        ctx.arc(x, y, 20, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(10, 10, 15, 0.8)';
        ctx.fill();
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.stroke();

        // Draw symbol
        ctx.font = '16px "Segoe UI", sans-serif';
        ctx.fillStyle = color;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(symbol, x, y);

        // Draw agent name
        ctx.font = '11px "Segoe UI", sans-serif';
        ctx.fillStyle = '#e0e0ff';
        ctx.fillText(agent.name || 'Unknown', x, y + 32);

        // Draw state label
        ctx.font = '10px "Segoe UI", sans-serif';
        ctx.fillStyle = color;
        ctx.fillText(`[${state}]`, x, y + 44);

        // Draw depth indicator
        if (agent.depth > 0) {
            ctx.font = '9px "Segoe UI", sans-serif';
            ctx.fillStyle = '#676e95';
            ctx.fillText(`d=${agent.depth}`, x, y + 55);
        }
    }

    draw() {
        const ctx = this.ctx;
        const w = this.canvas.width;
        const h = this.canvas.height;

        // Clear canvas
        ctx.clearRect(0, 0, w, h);

        // Draw background
        this.drawFractalBackground();

        if (!this.rootAgent || this.agents.size === 0) {
            ctx.font = '16px "Segoe UI", sans-serif';
            ctx.fillStyle = '#676e95';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('⏳ Waiting for agents...', w / 2, h / 2);
            return;
        }

        this.calculateLayout();

        // Draw connections
        for (const agent of this.agents.values()) {
            if (agent.children) {
                for (const child of agent.children) {
                    this.drawConnection(agent, child);
                }
            }
        }

        // Draw nodes
        for (const agent of this.agents.values()) {
            this.drawNode(agent);
        }
    }

    startAnimation() {
        const animate = () => {
            this.pulsePhase += 0.02;
            this.draw();
            this.animationId = requestAnimationFrame(animate);
        };
        animate();
    }

    stopAnimation() {
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
        }
    }
}

// Event Stream Manager
class EventStream {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.maxEvents = 50;
    }

    addEvent(event) {
        const eventType = event.event_type || 'unknown';
        const timestamp = event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : '--:--:--';
        const agentName = event.agent_name || '-';
        const message = event.message || '';

        const div = document.createElement('div');
        div.className = `event-item ${eventType}`;
        div.innerHTML = `
            <span class="event-timestamp">[${timestamp}]</span>
            <span class="event-type" style="color: ${this.getEventColor(eventType)}">${eventType}</span>
            ${agentName !== '-' ? `<span class="event-agent">${agentName}</span>` : ''}
            <span class="event-message">${message}</span>
        `;

        this.container.appendChild(div);

        // Remove old events
        while (this.container.children.length > this.maxEvents) {
            this.container.removeChild(this.container.firstChild);
        }

        // Auto-scroll to bottom
        this.container.scrollTop = this.container.scrollHeight;
    }

    getEventColor(eventType) {
        const colors = {
            agent_spawned: '#c3e88d',
            agent_state_changed: '#ffcb6b',
            wave_started: '#82aaff',
            wave_finished: '#82aaff',
            tool_called: '#ffcb6b',
            tool_result: '#c3e88d',
            delegation_created: '#c792ea',
            delegation_rejected: '#ff5372',
            delegation_result: '#c3e88d',
            task_started: '#82aaff',
            task_completed: '#c3e88d',
            task_failed: '#ff5372',
            plan_created: '#ffcb6b',
            replan_triggered: '#ff5372',
        };
        return colors[eventType] || '#e0e0ff';
    }
}

// WebSocket Connection Manager
class MonitorConnection {
    constructor(url, visualizer, eventStream) {
        this.url = url;
        this.visualizer = visualizer;
        this.eventStream = eventStream;
        this.ws = null;
        this.reconnectInterval = 3000;
        this.statusElement = document.getElementById('connection-status');
        this.taskElement = document.getElementById('task-id');
    }

    connect() {
        try {
            this.ws = new WebSocket(this.url);

            this.ws.onopen = () => {
                console.log('[Monitor] Connected to server');
                this.updateStatus('connected', 'Connected');
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleMessage(data);
                } catch (e) {
                    console.error('[Monitor] Failed to parse message:', e);
                }
            };

            this.ws.onclose = () => {
                console.log('[Monitor] Disconnected from server');
                this.updateStatus('disconnected', 'Disconnected');
                setTimeout(() => this.connect(), this.reconnectInterval);
            };

            this.ws.onerror = (error) => {
                console.error('[Monitor] WebSocket error:', error);
                this.updateStatus('disconnected', 'Error');
            };
        } catch (e) {
            console.error('[Monitor] Failed to connect:', e);
            setTimeout(() => this.connect(), this.reconnectInterval);
        }
    }

    handleMessage(data) {
        const type = data.type;

        if (type === 'event') {
            const event = data.data;
            this.eventStream.addEvent(event);

            // Update visualizer
            if (event.event_type === 'agent_spawned' && event.agent_id) {
                this.visualizer.addAgent({
                    id: event.agent_id,
                    name: event.agent_name,
                    role: event.agent_role,
                    parent_id: event.parent_agent_id,
                    state: event.state,
                    depth: event.depth,
                });
            } else if (event.event_type === 'agent_state_changed' && event.agent_id) {
                this.visualizer.updateAgentState(event.agent_id, event.state);
            }

            this.updateStats();
        } else if (type === 'snapshot') {
            const snapshot = data.data;
            if (snapshot.task_id) {
                this.taskElement.textContent = `Task: ${snapshot.task_id}`;
            }

            // Load all agents from snapshot
            for (const agent of Object.values(snapshot.agents || {})) {
                this.visualizer.addAgent(agent);
            }
            this.updateStats();
        } else if (type === 'task_set') {
            this.taskElement.textContent = `Task: ${data.task_id}`;
        }
    }

    updateStatus(status, text) {
        this.statusElement.className = `status ${status}`;
        this.statusElement.textContent = text;
    }

    updateStats() {
        const agents = this.visualizer.agents;
        const total = agents.size;
        const active = Array.from(agents.values()).filter(
            a => ['executing', 'delegating', 'planning', 'thinking'].includes(a.state)
        ).length;
        const maxDepth = Math.max(...Array.from(agents.values()).map(a => a.depth || 0), 0);

        document.getElementById('agent-count').textContent = `Agents: ${total}`;
        document.getElementById('active-count').textContent = `Active: ${active}`;
        document.getElementById('depth-count').textContent = `Depth: ${maxDepth}`;
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    const visualizer = new FractalTreeVisualizer('fractal-canvas');
    const eventStream = new EventStream('events-container');

    // Determine WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    // For development, use localhost:8765
    const devUrl = 'ws://127.0.0.1:8765';

    const connection = new MonitorConnection(devUrl, visualizer, eventStream);
    connection.connect();

    // Handle window resize
    window.addEventListener('resize', () => {
        visualizer.resize();
    });
});
