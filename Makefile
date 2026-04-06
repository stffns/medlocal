.PHONY: serve dev stop build test-es

# Start backend only (production)
serve:
	@pkill -f "medlocal" 2>/dev/null || true
	@sleep 1
	python -m medlocal.cli serve --port 8765 &>/tmp/medlocal.log &
	@echo "Backend: http://localhost:8765"

# Start backend + Vite dev server
dev: serve
	@cd frontend && npm run dev &>/tmp/vite.log &
	@sleep 2
	@echo "Frontend: http://localhost:5173"

# Stop everything
stop:
	@pkill -f "medlocal" 2>/dev/null || true
	@pkill -f "vite" 2>/dev/null || true
	@echo "Stopped"

# Build frontend for production
build:
	cd frontend && npm run build

# Quick smoke test — Spanish config
test-es:
	@echo "--- Consulta en español (language=Spanish en config) ---"
	@curl -s http://localhost:8765/api/consult \
		-H 'Content-Type: application/json' \
		-d '{"question":"Niño de 2 años con fiebre y sarpullido"}' \
		| python -m json.tool | head -20
