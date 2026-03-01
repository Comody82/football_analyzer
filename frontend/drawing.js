/**
 * Drawing System - Canvas Overlay per strumenti di disegno
 * Tools: Circle, Line, Arrow, Rectangle, Text
 */

class DrawingSystem {
    constructor(canvasId, videoContainerId) {
        this.canvas = document.getElementById(canvasId);
        this.videoContainer = document.getElementById(videoContainerId) || document.querySelector('.video-container');
        this.ctx = this.canvas.getContext('2d');
        
        // Drawing state
        this.tool = 'none'; // none, circle, line, arrow, rect, text
        this.isDrawing = false;
        this.startX = 0;
        this.startY = 0;
        this.currentX = 0;
        this.currentY = 0;
        
        // Drawing settings
        this.color = '#00ff00';
        this.thickness = 3;
        
        // Shapes storage
        this.shapes = [];
        this.tempShape = null;
        
        // Setup
        this.setupCanvas();
        this.bindEvents();
    }
    
    setupCanvas() {
        // Sincronizza dimensioni canvas con video container
        const resizeCanvas = () => {
            const rect = this.videoContainer.getBoundingClientRect();
            this.canvas.width = rect.width;
            this.canvas.height = rect.height;
            this.redraw();
        };
        
        resizeCanvas();
        window.addEventListener('resize', resizeCanvas);
    }
    
    bindEvents() {
        this.canvas.addEventListener('mousedown', (e) => this.handleMouseDown(e));
        this.canvas.addEventListener('mousemove', (e) => this.handleMouseMove(e));
        this.canvas.addEventListener('mouseup', (e) => this.handleMouseUp(e));
        this.canvas.addEventListener('mouseleave', () => this.handleMouseLeave());
    }
    
    setTool(tool) {
        this.tool = tool;
        this.canvas.classList.toggle('tool-none', tool === 'none');
        console.log(`🎨 Tool set: ${tool}`);
    }
    
    setColor(color) {
        this.color = color;
    }
    
    setThickness(thickness) {
        this.thickness = parseInt(thickness);
    }
    
    getMousePos(e) {
        const rect = this.canvas.getBoundingClientRect();
        return {
            x: e.clientX - rect.left,
            y: e.clientY - rect.top
        };
    }
    
    handleMouseDown(e) {
        if (this.tool === 'none') return;
        
        const pos = this.getMousePos(e);
        this.isDrawing = true;
        this.startX = pos.x;
        this.startY = pos.y;
        this.currentX = pos.x;
        this.currentY = pos.y;
        
        if (this.tool === 'text') {
            this.handleTextTool();
        }
    }
    
    handleMouseMove(e) {
        if (!this.isDrawing || this.tool === 'none' || this.tool === 'text') return;
        
        const pos = this.getMousePos(e);
        this.currentX = pos.x;
        this.currentY = pos.y;
        
        // Preview shape
        this.redraw();
        this.drawPreview();
    }
    
    handleMouseUp(e) {
        if (!this.isDrawing || this.tool === 'none' || this.tool === 'text') {
            this.isDrawing = false;
            return;
        }
        
        const pos = this.getMousePos(e);
        this.currentX = pos.x;
        this.currentY = pos.y;
        
        // Save shape
        const shape = {
            tool: this.tool,
            startX: this.startX,
            startY: this.startY,
            endX: this.currentX,
            endY: this.currentY,
            color: this.color,
            thickness: this.thickness
        };
        
        // Valida dimensioni minime
        const width = Math.abs(shape.endX - shape.startX);
        const height = Math.abs(shape.endY - shape.startY);
        if (width > 5 || height > 5) {
            this.shapes.push(shape);
            console.log(`✅ Shape saved: ${this.tool}`, shape);
        }
        
        this.isDrawing = false;
        this.redraw();
    }
    
    handleMouseLeave() {
        if (this.isDrawing && this.tool !== 'text') {
            this.isDrawing = false;
            this.redraw();
        }
    }
    
    handleTextTool() {
        const text = prompt('Inserisci testo:');
        if (text && text.trim()) {
            const shape = {
                tool: 'text',
                x: this.startX,
                y: this.startY,
                text: text.trim(),
                color: this.color,
                thickness: this.thickness
            };
            this.shapes.push(shape);
            this.redraw();
            console.log(`✅ Text added: "${text}"`);
        }
        this.isDrawing = false;
    }
    
    drawPreview() {
        this.ctx.strokeStyle = this.color;
        this.ctx.fillStyle = this.color;
        this.ctx.lineWidth = this.thickness;
        this.ctx.lineCap = 'round';
        this.ctx.lineJoin = 'round';
        
        switch (this.tool) {
            case 'circle':
                this.drawCircle(this.startX, this.startY, this.currentX, this.currentY);
                break;
            case 'line':
                this.drawLine(this.startX, this.startY, this.currentX, this.currentY);
                break;
            case 'arrow':
                this.drawArrow(this.startX, this.startY, this.currentX, this.currentY);
                break;
            case 'rect':
                this.drawRect(this.startX, this.startY, this.currentX, this.currentY);
                break;
        }
    }
    
    drawCircle(x1, y1, x2, y2) {
        const radius = Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
        this.ctx.beginPath();
        this.ctx.arc(x1, y1, radius, 0, Math.PI * 2);
        this.ctx.stroke();
    }
    
    drawLine(x1, y1, x2, y2) {
        this.ctx.beginPath();
        this.ctx.moveTo(x1, y1);
        this.ctx.lineTo(x2, y2);
        this.ctx.stroke();
    }
    
    drawArrow(x1, y1, x2, y2) {
        // Disegna linea
        this.drawLine(x1, y1, x2, y2);
        
        // Disegna punta freccia
        const angle = Math.atan2(y2 - y1, x2 - x1);
        const arrowLength = 15 + this.thickness;
        const arrowWidth = 8 + this.thickness;
        
        this.ctx.beginPath();
        this.ctx.moveTo(x2, y2);
        this.ctx.lineTo(
            x2 - arrowLength * Math.cos(angle - Math.PI / 6),
            y2 - arrowLength * Math.sin(angle - Math.PI / 6)
        );
        this.ctx.moveTo(x2, y2);
        this.ctx.lineTo(
            x2 - arrowLength * Math.cos(angle + Math.PI / 6),
            y2 - arrowLength * Math.sin(angle + Math.PI / 6)
        );
        this.ctx.stroke();
    }
    
    drawRect(x1, y1, x2, y2) {
        const width = x2 - x1;
        const height = y2 - y1;
        this.ctx.strokeRect(x1, y1, width, height);
    }
    
    drawText(x, y, text, color, thickness) {
        this.ctx.fillStyle = color;
        this.ctx.font = `${16 + thickness * 2}px Arial`;
        this.ctx.fillText(text, x, y);
    }
    
    redraw() {
        // Clear canvas
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        
        // Draw all saved shapes
        this.shapes.forEach(shape => {
            this.ctx.strokeStyle = shape.color;
            this.ctx.fillStyle = shape.color;
            this.ctx.lineWidth = shape.thickness;
            this.ctx.lineCap = 'round';
            this.ctx.lineJoin = 'round';
            
            switch (shape.tool) {
                case 'circle':
                    this.drawCircle(shape.startX, shape.startY, shape.endX, shape.endY);
                    break;
                case 'line':
                    this.drawLine(shape.startX, shape.startY, shape.endX, shape.endY);
                    break;
                case 'arrow':
                    this.drawArrow(shape.startX, shape.startY, shape.endX, shape.endY);
                    break;
                case 'rect':
                    this.drawRect(shape.startX, shape.startY, shape.endX, shape.endY);
                    break;
                case 'text':
                    this.drawText(shape.x, shape.y, shape.text, shape.color, shape.thickness);
                    break;
            }
        });
    }
    
    clearAll() {
        this.shapes = [];
        this.redraw();
        console.log('🗑️ All drawings cleared');
    }
    
    getShapes() {
        return JSON.stringify(this.shapes);
    }
    
    loadShapes(shapesJson) {
        try {
            this.shapes = JSON.parse(shapesJson);
            this.redraw();
            console.log(`✅ Loaded ${this.shapes.length} shapes`);
        } catch (e) {
            console.error('Failed to load shapes:', e);
        }
    }
}

// Export per uso globale
window.DrawingSystem = DrawingSystem;
