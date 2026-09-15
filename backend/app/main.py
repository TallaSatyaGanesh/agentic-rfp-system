from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.db.database import engine, Base
from app.api.rfp_routes import router as rfp_router
from app.api.workflow_routes import router as workflow_router
from app.api.knowledge_routes import router as knowledge_router

# Initialize database schema
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Agentic AI RFP Analysis & Proposal Response System",
    description="Multi-agent orchestrator for RFP ingestion, requirement classification, compliance RAG audit, risk analysis, and iterative proposal generation.",
    version="1.0.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(rfp_router)
app.include_router(workflow_router)
app.include_router(knowledge_router)

@app.get("/")
def root():
    return {
        "system": "Agentic AI RFP Analysis & Proposal Response System",
        "status": "online",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "database": "sqlite_connected"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
