# Research Report: MCP Tools Layer Refactoring

## Design Evaluations & Decisions

### 1. Dependency Injection (FastDepends vs Custom DI)
- **Decision**: Use standard constructor-based dependency injection for services and repositories, and a lightweight context manager/decorator for tool endpoint injection.
- **Rationale**: FastDepends adds unnecessary dependency overhead and can mask type-checking. A custom constructor-based DI is 100% type-safe, utilizes standard Python types, and is easily unit-tested.
- **Alternatives Considered**: FastDepends (rejected due to dependency overhead).

### 2. Transaction Management (Repository vs Unit of Work)
- **Decision**: Use the Repository pattern for database queries/mutations. Implement a lightweight session context context manager for services to scope transactional boundaries.
- **Rationale**: Decouples query orchestration from business flow, while keeping transaction commits scoped at the service/use-case boundary.
- **Alternatives Considered**: Unit of Work pattern (deemed overly complex for our current tool requirements).

### 3. Service Layer Boundaries
- **Decision**: Services accept repositories and user context via constructor injection. They return validated Pydantic DTO models and throw domain-specific exceptions.
- **Rationale**: Isolates business rule orchestration from the Starlette/FastMCP transport layer.

### 4. Centralized Exception Translation
- **Decision**: A unified `@translate_mcp_exceptions` decorator wraps all registered FastMCP tools.
- **Rationale**: Translates custom exceptions (e.g., `NotFoundError`, `PermissionDeniedError`) into unified `ErrorResponse` schemas, removing repeated try-except blocks.

### 5. SQLAlchemy Async Best Practices
- **Decision**: Use `selectinload` for lazy relationships and ensure all database transactions are managed via `async with session.begin()`.
