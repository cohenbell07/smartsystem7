"""
Coding Orchestrator: The World's Smartest Multi-Agent Coding System

This module implements a fully autonomous coding orchestration system that:
1. Takes natural language prompts and generates production-ready codebases
2. Coordinates specialized AI Coder Agents (frontend, backend, database, API)
3. Implements self-correction loops with validation feedback
4. Learns from past builds through evaluation tracking
5. Ensures zero-error code through iterative refinement

Architecture:
- Manager Agent: Coordinates the entire build process
- Specialized Coders: Frontend, Backend, Database, API, Testing, DevOps
- Validator Agent: Reviews code quality, security, and correctness
- Self-Correction Loop: Iterates until code is perfect
- Memory System: Learns from past builds
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)


class CoderSpecialty(str, Enum):
    """Specialized coder agent types."""
    FRONTEND = "frontend"
    BACKEND = "backend"
    DATABASE = "database"
    API = "api"
    TESTING = "testing"
    DEVOPS = "devops"
    SECURITY = "security"
    DOCUMENTATION = "documentation"


@dataclass
class CoderProfile:
    """Profile for a specialized coder agent."""
    specialty: CoderSpecialty
    name: str
    description: str
    expertise: List[str]
    tools: List[str]
    languages: List[str]
    frameworks: List[str]
    prompt_template: str
    validation_criteria: List[str]


class CoderRegistry:
    """Registry of specialized coder agent profiles."""

    PROFILES = {
        CoderSpecialty.FRONTEND: CoderProfile(
            specialty=CoderSpecialty.FRONTEND,
            name="Frontend Developer Agent",
            description="Expert in building modern, responsive user interfaces",
            expertise=[
                "React", "Next.js", "TypeScript", "Tailwind CSS",
                "State Management", "Component Architecture", "Accessibility",
                "Performance Optimization", "Responsive Design"
            ],
            tools=["code_executor", "browser", "github", "file_writer"],
            languages=["TypeScript", "JavaScript", "HTML", "CSS"],
            frameworks=["React", "Next.js", "Vue", "Svelte"],
            prompt_template="""You are an elite Frontend Developer Agent specializing in modern web development.

**Your Mission**: {task_description}

**Project Context**:
{project_context}

**Requirements**:
{requirements}

**Tech Stack**:
- Framework: {frontend_framework}
- Styling: {styling_approach}
- State Management: {state_management}

**Previous Work from Team**:
{team_outputs}

**Quality Standards**:
1. Write clean, maintainable TypeScript code
2. Follow best practices for component architecture
3. Ensure accessibility (WCAG 2.1 AA)
4. Optimize for performance (Core Web Vitals)
5. Make it responsive and mobile-first
6. Add proper error handling and loading states
7. Include comments for complex logic

**Validation Feedback** (if any):
{validation_feedback}

Provide your implementation with:
1. Complete file structure
2. All component code
3. Tests for critical components
4. README with setup instructions
""",
            validation_criteria=[
                "Code compiles without errors",
                "No accessibility violations",
                "Responsive design works on all screen sizes",
                "Performance metrics meet standards",
                "Code follows style guide",
                "Components are properly typed"
            ]
        ),

        CoderSpecialty.BACKEND: CoderProfile(
            specialty=CoderSpecialty.BACKEND,
            name="Backend Developer Agent",
            description="Expert in building scalable, secure server-side applications",
            expertise=[
                "FastAPI", "Django", "Flask", "Node.js/Express",
                "REST APIs", "GraphQL", "Authentication", "Authorization",
                "Microservices", "Message Queues", "Caching", "Rate Limiting"
            ],
            tools=["code_executor", "github", "file_writer", "api_caller"],
            languages=["Python", "TypeScript", "Go", "Rust"],
            frameworks=["FastAPI", "Django", "Express", "NestJS"],
            prompt_template="""You are an elite Backend Developer Agent specializing in server-side development.

**Your Mission**: {task_description}

**Project Context**:
{project_context}

**Requirements**:
{requirements}

**Tech Stack**:
- Framework: {backend_framework}
- Database: {database_type}
- Authentication: {auth_method}
- Deployment: {deployment_target}

**Database Schema** (from Database Agent):
{database_schema}

**API Contract** (from API Agent):
{api_contract}

**Previous Work from Team**:
{team_outputs}

**Quality Standards**:
1. Write secure, production-ready code
2. Implement proper error handling and logging
3. Add input validation and sanitization
4. Follow SOLID principles
5. Write comprehensive tests (unit + integration)
6. Document all endpoints
7. Optimize database queries
8. Implement rate limiting and caching

**Validation Feedback** (if any):
{validation_feedback}

Provide your implementation with:
1. Complete file structure
2. All route handlers and business logic
3. Middleware and utilities
4. Tests with >80% coverage
5. OpenAPI/Swagger documentation
6. Deployment configuration
""",
            validation_criteria=[
                "All tests pass",
                "No security vulnerabilities",
                "API endpoints follow REST conventions",
                "Error handling is comprehensive",
                "Code coverage >80%",
                "Performance benchmarks met"
            ]
        ),

        CoderSpecialty.DATABASE: CoderProfile(
            specialty=CoderSpecialty.DATABASE,
            name="Database Engineer Agent",
            description="Expert in database design, optimization, and data modeling",
            expertise=[
                "PostgreSQL", "MySQL", "MongoDB", "Redis",
                "Schema Design", "Indexing", "Query Optimization",
                "Migrations", "Replication", "Sharding", "Data Integrity"
            ],
            tools=["code_executor", "file_writer"],
            languages=["SQL", "Python"],
            frameworks=["SQLModel", "Prisma", "TypeORM", "Alembic"],
            prompt_template="""You are an elite Database Engineer Agent specializing in data architecture.

**Your Mission**: {task_description}

**Project Context**:
{project_context}

**Requirements**:
{requirements}

**Data Requirements**:
{data_requirements}

**Previous Work from Team**:
{team_outputs}

**Quality Standards**:
1. Design normalized, efficient schemas
2. Create proper indexes for performance
3. Implement data integrity constraints
4. Write safe migration scripts
5. Document all tables and relationships
6. Plan for scalability
7. Consider data privacy and security

**Validation Feedback** (if any):
{validation_feedback}

Provide your implementation with:
1. Complete schema definitions
2. Migration scripts
3. Indexing strategy
4. Sample queries for common operations
5. ER diagram (text description)
6. Seed data for testing
""",
            validation_criteria=[
                "Schema is properly normalized",
                "Indexes are optimized",
                "Constraints ensure data integrity",
                "Migrations are reversible",
                "No N+1 query issues"
            ]
        ),

        CoderSpecialty.API: CoderProfile(
            specialty=CoderSpecialty.API,
            name="API Design Agent",
            description="Expert in API architecture, design patterns, and integration",
            expertise=[
                "REST API Design", "GraphQL", "OpenAPI/Swagger",
                "API Versioning", "Rate Limiting", "API Security",
                "Webhooks", "WebSockets", "API Documentation"
            ],
            tools=["code_executor", "api_caller", "file_writer"],
            languages=["Python", "TypeScript", "YAML"],
            frameworks=["FastAPI", "Express", "GraphQL"],
            prompt_template="""You are an elite API Design Agent specializing in API architecture.

**Your Mission**: {task_description}

**Project Context**:
{project_context}

**Requirements**:
{requirements}

**Database Schema**:
{database_schema}

**Frontend Requirements**:
{frontend_requirements}

**Previous Work from Team**:
{team_outputs}

**Quality Standards**:
1. Design RESTful, intuitive APIs
2. Follow API design best practices
3. Implement proper versioning
4. Add comprehensive documentation
5. Include request/response examples
6. Design for backward compatibility
7. Consider rate limiting and pagination

**Validation Feedback** (if any):
{validation_feedback}

Provide your implementation with:
1. Complete API specification (OpenAPI 3.0)
2. Endpoint definitions with examples
3. Authentication/authorization flows
4. Error response formats
5. Rate limiting strategy
6. Versioning approach
""",
            validation_criteria=[
                "API follows REST conventions",
                "All endpoints documented",
                "Response formats are consistent",
                "Error handling is standardized",
                "Security best practices followed"
            ]
        ),

        CoderSpecialty.TESTING: CoderProfile(
            specialty=CoderSpecialty.TESTING,
            name="QA Engineer Agent",
            description="Expert in testing strategies, test automation, and quality assurance",
            expertise=[
                "Unit Testing", "Integration Testing", "E2E Testing",
                "Test Automation", "Jest", "Pytest", "Playwright",
                "Load Testing", "Security Testing", "Test Coverage"
            ],
            tools=["code_executor", "browser", "file_writer"],
            languages=["Python", "TypeScript", "JavaScript"],
            frameworks=["Pytest", "Jest", "Playwright", "Locust"],
            prompt_template="""You are an elite QA Engineer Agent specializing in comprehensive testing.

**Your Mission**: {task_description}

**Project Context**:
{project_context}

**Codebase to Test**:
{codebase_summary}

**Previous Work from Team**:
{team_outputs}

**Quality Standards**:
1. Write comprehensive test suites
2. Achieve >80% code coverage
3. Include unit, integration, and E2E tests
4. Test edge cases and error scenarios
5. Perform security testing
6. Test performance under load
7. Document test scenarios

**Validation Feedback** (if any):
{validation_feedback}

Provide your implementation with:
1. Complete test suite structure
2. Unit tests for all critical functions
3. Integration tests for API endpoints
4. E2E tests for user workflows
5. Performance/load test scenarios
6. Test coverage report strategy
7. CI/CD integration instructions
""",
            validation_criteria=[
                "Test coverage >80%",
                "All critical paths tested",
                "Tests pass consistently",
                "Performance tests validate requirements",
                "Security tests pass"
            ]
        ),

        CoderSpecialty.DEVOPS: CoderProfile(
            specialty=CoderSpecialty.DEVOPS,
            name="DevOps Engineer Agent",
            description="Expert in deployment, CI/CD, infrastructure, and monitoring",
            expertise=[
                "Docker", "Kubernetes", "CI/CD", "GitHub Actions",
                "AWS/GCP/Azure", "Terraform", "Monitoring", "Logging",
                "Load Balancing", "Auto-scaling", "Secrets Management"
            ],
            tools=["code_executor", "github", "file_writer"],
            languages=["YAML", "Bash", "Python", "HCL"],
            frameworks=["Docker", "Kubernetes", "Terraform", "GitHub Actions"],
            prompt_template="""You are an elite DevOps Engineer Agent specializing in deployment and infrastructure.

**Your Mission**: {task_description}

**Project Context**:
{project_context}

**Application Stack**:
{application_stack}

**Deployment Target**:
{deployment_target}

**Previous Work from Team**:
{team_outputs}

**Quality Standards**:
1. Containerize applications properly
2. Set up robust CI/CD pipelines
3. Implement monitoring and alerting
4. Configure auto-scaling
5. Secure secrets management
6. Set up logging and observability
7. Document deployment processes

**Validation Feedback** (if any):
{validation_feedback}

Provide your implementation with:
1. Dockerfile(s) for all services
2. docker-compose.yml for local development
3. Kubernetes manifests (if applicable)
4. CI/CD pipeline configuration
5. Infrastructure as Code (Terraform/CloudFormation)
6. Monitoring setup (Prometheus/Grafana)
7. Deployment runbook
""",
            validation_criteria=[
                "Containers build successfully",
                "CI/CD pipeline runs without errors",
                "Deployment is reproducible",
                "Monitoring is comprehensive",
                "Security best practices followed"
            ]
        ),

        CoderSpecialty.SECURITY: CoderProfile(
            specialty=CoderSpecialty.SECURITY,
            name="Security Engineer Agent",
            description="Expert in application security, vulnerability assessment, and secure coding",
            expertise=[
                "OWASP Top 10", "Penetration Testing", "Security Audits",
                "Encryption", "Authentication", "Authorization",
                "Dependency Scanning", "SAST/DAST", "Security Headers"
            ],
            tools=["code_executor", "file_writer"],
            languages=["Python", "JavaScript", "YAML"],
            frameworks=["OWASP ZAP", "Bandit", "ESLint Security"],
            prompt_template="""You are an elite Security Engineer Agent specializing in application security.

**Your Mission**: {task_description}

**Project Context**:
{project_context}

**Codebase to Audit**:
{codebase_summary}

**Previous Work from Team**:
{team_outputs}

**Quality Standards**:
1. Identify all security vulnerabilities
2. Verify OWASP Top 10 compliance
3. Check authentication/authorization
4. Review data encryption
5. Scan dependencies for vulnerabilities
6. Validate input sanitization
7. Provide remediation guidance

**Validation Feedback** (if any):
{validation_feedback}

Provide your security assessment with:
1. Comprehensive vulnerability report
2. Risk assessment (Critical/High/Medium/Low)
3. Remediation recommendations
4. Security test suite
5. Security configuration checklist
6. Compliance verification (GDPR, SOC2, etc.)
""",
            validation_criteria=[
                "No critical vulnerabilities",
                "OWASP Top 10 compliance verified",
                "Secrets not hardcoded",
                "Dependencies have no known CVEs",
                "Security headers configured"
            ]
        ),

        CoderSpecialty.DOCUMENTATION: CoderProfile(
            specialty=CoderSpecialty.DOCUMENTATION,
            name="Technical Writer Agent",
            description="Expert in creating comprehensive, user-friendly documentation",
            expertise=[
                "Technical Writing", "API Documentation", "User Guides",
                "Architecture Diagrams", "README Files", "Tutorials",
                "Code Comments", "Markdown", "Documentation Sites"
            ],
            tools=["file_writer"],
            languages=["Markdown", "HTML"],
            frameworks=["MkDocs", "Docusaurus", "Sphinx"],
            prompt_template="""You are an elite Technical Writer Agent specializing in developer documentation.

**Your Mission**: {task_description}

**Project Context**:
{project_context}

**Codebase to Document**:
{codebase_summary}

**Previous Work from Team**:
{team_outputs}

**Quality Standards**:
1. Write clear, concise documentation
2. Include getting started guide
3. Document all APIs comprehensively
4. Add code examples for common use cases
5. Create architecture diagrams (text-based)
6. Write deployment instructions
7. Include troubleshooting guide

**Validation Feedback** (if any):
{validation_feedback}

Provide your documentation with:
1. Comprehensive README.md
2. API reference documentation
3. Getting started guide
4. Architecture overview
5. Deployment guide
6. Contributing guidelines
7. Troubleshooting section
""",
            validation_criteria=[
                "Documentation is complete",
                "All APIs documented",
                "Examples are accurate",
                "Instructions are clear",
                "No broken links"
            ]
        )
    }

    @classmethod
    def get_profile(cls, specialty: CoderSpecialty) -> CoderProfile:
        """Get the profile for a coder specialty."""
        return cls.PROFILES.get(specialty)

    @classmethod
    def get_all_profiles(cls) -> Dict[CoderSpecialty, CoderProfile]:
        """Get all coder profiles."""
        return cls.PROFILES


@dataclass
class ValidationResult:
    """Result of code validation."""
    passed: bool
    score: float  # 0.0 to 1.0
    issues: List[Dict[str, Any]]
    improvements: List[str]
    critical_errors: List[str]
    warnings: List[str]
    feedback: str


@dataclass
class BuildIteration:
    """Represents one iteration of the build process."""
    iteration_number: int
    coders_executed: List[CoderSpecialty]
    outputs: Dict[str, Any]
    validation_result: ValidationResult
    improvements_made: List[str]
    duration: float


class CodingOrchestrator:
    """
    The World's Smartest Coding Orchestrator.

    Coordinates specialized AI coder agents to autonomously build
    production-ready codebases from natural language prompts.
    """

    def __init__(self, llm_router, tools: Dict[str, Any], vector_memory):
        """
        Initialize the Coding Orchestrator.

        Args:
            llm_router: LLM router for generating responses
            tools: Dictionary of available tools
            vector_memory: Vector memory for learning from past builds
        """
        self.llm_router = llm_router
        self.tools = tools
        self.vector_memory = vector_memory
        self.registry = CoderRegistry()
        self.max_iterations = 5  # Maximum self-correction iterations
        self.target_quality_score = 0.95  # 95% quality threshold

    async def parse_build_requirements(
        self,
        user_prompt: str,
        project_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Parse user prompt to determine build requirements and execution plan.

        Args:
            user_prompt: Natural language description of what to build
            project_context: Optional context about the project

        Returns:
            Parsed build requirements including tech stack, features, and agents needed
        """
        try:
            logger.info("Parsing build requirements from user prompt")

            # Recall relevant past builds
            recalled_builds = await self._recall_similar_builds(user_prompt)

            parse_prompt = f"""You are analyzing a coding project request to determine the optimal implementation strategy.

**User Request**: {user_prompt}

**Project Context**: {json.dumps(project_context or {}, indent=2)}

**Similar Past Builds**:
{self._format_recalled_builds(recalled_builds)}

Based on this request, determine:

1. **Project Type**: (web app, API, CLI tool, library, mobile app, etc.)
2. **Tech Stack**:
   - Frontend framework (React, Next.js, Vue, etc.) if applicable
   - Backend framework (FastAPI, Django, Express, etc.) if applicable
   - Database (PostgreSQL, MongoDB, Redis, etc.) if applicable
   - Other technologies needed

3. **Required Features**: List all features that need to be implemented

4. **Specialized Coders Needed**: Which of these agents should be activated?
   - frontend: Frontend Developer
   - backend: Backend Developer
   - database: Database Engineer
   - api: API Design Expert
   - testing: QA Engineer
   - devops: DevOps Engineer
   - security: Security Auditor
   - documentation: Technical Writer

5. **Execution Order**: What's the optimal sequence for building this?

6. **Complexity Estimate**: (low/medium/high/very_high)

7. **Estimated Lines of Code**: Approximate total LOC

8. **Quality Requirements**: Performance, security, scalability needs

Respond in JSON format:
{{
    "project_type": "...",
    "project_name": "...",
    "tech_stack": {{
        "frontend": "...",
        "backend": "...",
        "database": "...",
        "other": ["..."]
    }},
    "features": ["...", "..."],
    "required_coders": ["frontend", "backend", "database", "api", "testing", "devops", "security", "documentation"],
    "execution_order": [
        {{"coder": "database", "reason": "..."}},
        {{"coder": "api", "reason": "..."}},
        {{"coder": "backend", "reason": "..."}},
        {{"coder": "frontend", "reason": "..."}}
    ],
    "complexity": "medium",
    "estimated_loc": 5000,
    "quality_requirements": {{
        "performance": "...",
        "security": "...",
        "scalability": "..."
    }}
}}"""

            response = await self.llm_router.generate(
                prompt=parse_prompt,
                model="gpt-4",
                temperature=0.3
            )

            content = response.get("content", "")
            start_idx = content.find("{")
            end_idx = content.rfind("}") + 1

            if start_idx >= 0 and end_idx > start_idx:
                parsed = json.loads(content[start_idx:end_idx])
                logger.info(f"Parsed build requirements: {parsed.get('project_name', 'unknown')}")
                return parsed
            else:
                logger.warning("Could not parse build requirements JSON, using defaults")
                return self._default_build_requirements(user_prompt)

        except Exception as e:
            logger.error(f"Error parsing build requirements: {e}")
            return self._default_build_requirements(user_prompt)

    async def _recall_similar_builds(self, user_prompt: str) -> List[Dict[str, Any]]:
        """Recall similar past builds from memory."""
        try:
            recalled = self.vector_memory.recall(
                context_query=user_prompt,
                n_results=3,
                agent_id=None  # Global memory across all builds
            )
            logger.info(f"Recalled {len(recalled)} similar past builds")
            return recalled
        except Exception as e:
            logger.error(f"Error recalling past builds: {e}")
            return []

    def _format_recalled_builds(self, recalled: List[Dict[str, Any]]) -> str:
        """Format recalled builds for prompt injection."""
        if not recalled:
            return "No similar past builds found."

        lines = []
        for i, build in enumerate(recalled, 1):
            score = build.get("relevance_score", 0)
            text = build.get("text", "")
            lines.append(f"{i}. [Relevance: {score:.2f}] {text[:300]}...")

        return "\n".join(lines)

    def _default_build_requirements(self, user_prompt: str) -> Dict[str, Any]:
        """Provide default build requirements when parsing fails."""
        return {
            "project_type": "web_app",
            "project_name": "custom_project",
            "tech_stack": {
                "frontend": "React + Next.js",
                "backend": "FastAPI",
                "database": "PostgreSQL"
            },
            "features": ["Parse from user prompt"],
            "required_coders": ["database", "api", "backend", "frontend", "testing", "documentation"],
            "execution_order": [
                {"coder": "database", "reason": "Define data models first"},
                {"coder": "api", "reason": "Design API contract"},
                {"coder": "backend", "reason": "Implement server logic"},
                {"coder": "frontend", "reason": "Build user interface"},
                {"coder": "testing", "reason": "Ensure quality"},
                {"coder": "documentation", "reason": "Document the system"}
            ],
            "complexity": "medium",
            "estimated_loc": 3000,
            "quality_requirements": {
                "performance": "Fast response times",
                "security": "Standard security practices",
                "scalability": "Handle moderate load"
            }
        }

    async def execute_coder(
        self,
        specialty: CoderSpecialty,
        task_description: str,
        context: Dict[str, Any],
        validation_feedback: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a specialized coder agent.

        Args:
            specialty: The type of coder to execute
            task_description: What the coder should build
            context: Build context (requirements, team outputs, etc.)
            validation_feedback: Feedback from previous validation (if iterating)

        Returns:
            Coder output including code, files, and metadata
        """
        try:
            profile = self.registry.get_profile(specialty)
            if not profile:
                return {"error": f"Unknown coder specialty: {specialty}"}

            logger.info(f"Executing {profile.name}")

            # Build the prompt for this coder
            prompt = profile.prompt_template.format(
                task_description=task_description,
                project_context=context.get("project_context", {}),
                requirements=context.get("requirements", ""),
                team_outputs=self._format_team_outputs(context.get("team_outputs", {})),
                validation_feedback=validation_feedback or "No previous feedback - first iteration",
                frontend_framework=context.get("tech_stack", {}).get("frontend", "React"),
                styling_approach=context.get("styling", "Tailwind CSS"),
                state_management=context.get("state_management", "React hooks"),
                backend_framework=context.get("tech_stack", {}).get("backend", "FastAPI"),
                database_type=context.get("tech_stack", {}).get("database", "PostgreSQL"),
                auth_method=context.get("auth_method", "JWT"),
                deployment_target=context.get("deployment", "Docker"),
                database_schema=context.get("database_schema", "Not yet defined"),
                api_contract=context.get("api_contract", "Not yet defined"),
                data_requirements=context.get("data_requirements", ""),
                frontend_requirements=context.get("frontend_requirements", ""),
                application_stack=context.get("application_stack", ""),
                codebase_summary=context.get("codebase_summary", "")
            )

            # Execute with LLM
            response = await self.llm_router.generate(
                prompt=prompt,
                model=context.get("model", "gpt-4"),
                temperature=0.7,
                max_tokens=8000  # Allow long code outputs
            )

            output = response.get("content", "")

            result = {
                "specialty": specialty.value,
                "agent_name": profile.name,
                "output": output,
                "tokens_used": response.get("usage", {}),
                "success": True,
                "files_generated": self._extract_files_from_output(output),
                "validation_criteria": profile.validation_criteria
            }

            logger.info(f"{profile.name} completed successfully")
            return result

        except Exception as e:
            logger.error(f"Error executing coder {specialty}: {e}")
            return {
                "specialty": specialty.value,
                "error": str(e),
                "success": False
            }

    def _format_team_outputs(self, team_outputs: Dict[str, Any]) -> str:
        """Format outputs from other team members for context."""
        if not team_outputs:
            return "No previous work from team yet."

        lines = []
        for coder, output in team_outputs.items():
            if isinstance(output, dict) and output.get("success"):
                lines.append(f"\n## {coder.upper()} OUTPUT:\n{output.get('output', '')[:1000]}...")

        return "\n".join(lines) if lines else "No previous work from team yet."

    def _extract_files_from_output(self, output: str) -> List[Dict[str, str]]:
        """
        Extract file definitions from coder output.

        Looks for patterns like:
        ```filename
        content
        ```
        """
        files = []
        # This is a simplified version - in production would use more robust parsing
        return files

    async def validate_build(
        self,
        build_outputs: Dict[str, Any],
        requirements: Dict[str, Any]
    ) -> ValidationResult:
        """
        Validate the entire build for quality, correctness, and completeness.

        Args:
            build_outputs: Outputs from all coder agents
            requirements: Original build requirements

        Returns:
            Validation result with pass/fail, issues, and feedback
        """
        try:
            logger.info("Validating build quality")

            # Compile all outputs
            all_code = ""
            for coder, output in build_outputs.items():
                if isinstance(output, dict) and output.get("success"):
                    all_code += f"\n\n=== {coder.upper()} ===\n{output.get('output', '')}"

            validation_prompt = f"""You are an elite Code Quality Validator. Your job is to review code and ensure it meets the highest standards.

**Original Requirements**:
{json.dumps(requirements, indent=2)}

**Complete Codebase**:
{all_code[:15000]}  # Limit to avoid token limits

**Validation Checklist**:
1. **Completeness**: Are all required features implemented?
2. **Correctness**: Does the code work as intended?
3. **Quality**: Is the code well-structured and maintainable?
4. **Security**: Are there any security vulnerabilities?
5. **Performance**: Are there obvious performance issues?
6. **Testing**: Is the code testable/tested?
7. **Documentation**: Is the code properly documented?
8. **Best Practices**: Does it follow language/framework best practices?

Respond in JSON format:
{{
    "passed": true/false,
    "score": 0.0-1.0,
    "issues": [
        {{"severity": "critical|high|medium|low", "category": "...", "description": "...", "location": "...", "fix": "..."}},
        ...
    ],
    "improvements": ["...", "..."],
    "critical_errors": ["...", "..."],
    "warnings": ["...", "..."],
    "feedback": "Detailed feedback for the team to improve..."
}}"""

            response = await self.llm_router.generate(
                prompt=validation_prompt,
                model="gpt-4",
                temperature=0.3
            )

            content = response.get("content", "")
            start_idx = content.find("{")
            end_idx = content.rfind("}") + 1

            if start_idx >= 0 and end_idx > start_idx:
                result_dict = json.loads(content[start_idx:end_idx])

                validation = ValidationResult(
                    passed=result_dict.get("passed", False),
                    score=result_dict.get("score", 0.0),
                    issues=result_dict.get("issues", []),
                    improvements=result_dict.get("improvements", []),
                    critical_errors=result_dict.get("critical_errors", []),
                    warnings=result_dict.get("warnings", []),
                    feedback=result_dict.get("feedback", "")
                )

                logger.info(f"Validation complete: {'PASSED' if validation.passed else 'FAILED'} (score: {validation.score:.2f})")
                return validation
            else:
                # Fallback validation
                return ValidationResult(
                    passed=False,
                    score=0.5,
                    issues=[],
                    improvements=["Could not parse validation results"],
                    critical_errors=[],
                    warnings=[],
                    feedback="Validation parsing failed"
                )

        except Exception as e:
            logger.error(f"Error during validation: {e}")
            return ValidationResult(
                passed=False,
                score=0.0,
                issues=[],
                improvements=[],
                critical_errors=[str(e)],
                warnings=[],
                feedback=f"Validation error: {e}"
            )

    async def orchestrate_build(
        self,
        user_prompt: str,
        project_context: Optional[Dict[str, Any]] = None,
        log_callback=None
    ) -> Dict[str, Any]:
        """
        Main orchestration method: Build a complete codebase from a natural language prompt.

        This implements the full workflow:
        1. Parse requirements
        2. Execute coders in optimal order
        3. Validate the build
        4. Self-correct if needed (iterate up to max_iterations)
        5. Store learnings in memory

        Args:
            user_prompt: Natural language description of what to build
            project_context: Optional additional context
            log_callback: Optional callback for streaming logs

        Returns:
            Complete build result including all code, validation, and metadata
        """
        try:
            if log_callback:
                await log_callback("🚀 Starting Coding Orchestration System")
                await log_callback(f"📝 User Request: {user_prompt[:200]}...")

            logger.info(f"Starting build orchestration for: {user_prompt[:100]}...")

            # Step 1: Parse requirements
            if log_callback:
                await log_callback("\n📋 Parsing build requirements...")

            requirements = await self.parse_build_requirements(user_prompt, project_context)

            if log_callback:
                await log_callback(f"✅ Project: {requirements.get('project_name', 'unknown')}")
                await log_callback(f"   Type: {requirements.get('project_type', 'unknown')}")
                await log_callback(f"   Complexity: {requirements.get('complexity', 'unknown')}")
                await log_callback(f"   Coders needed: {len(requirements.get('required_coders', []))}")

            # Step 2: Iterative build with self-correction
            iterations = []
            current_outputs = {}
            context = {
                "project_context": requirements,
                "requirements": json.dumps(requirements.get("features", []), indent=2),
                "tech_stack": requirements.get("tech_stack", {}),
                "team_outputs": {}
            }

            for iteration in range(1, self.max_iterations + 1):
                if log_callback:
                    await log_callback(f"\n🔄 Build Iteration {iteration}/{self.max_iterations}")

                iteration_start = asyncio.get_event_loop().time()
                iteration_outputs = {}

                # Execute coders in order
                execution_order = requirements.get("execution_order", [])
                for step in execution_order:
                    coder_type = step.get("coder")
                    reason = step.get("reason", "")

                    try:
                        specialty = CoderSpecialty(coder_type)
                    except ValueError:
                        logger.warning(f"Unknown coder type: {coder_type}")
                        continue

                    if log_callback:
                        await log_callback(f"   👨‍💻 {specialty.value.upper()}: {reason}")

                    # Get validation feedback from previous iteration
                    validation_feedback = None
                    if iteration > 1 and iterations:
                        prev_validation = iterations[-1].validation_result
                        validation_feedback = prev_validation.feedback

                    # Execute the coder
                    result = await self.execute_coder(
                        specialty=specialty,
                        task_description=f"Build {specialty.value} for: {user_prompt}",
                        context=context,
                        validation_feedback=validation_feedback
                    )

                    iteration_outputs[coder_type] = result
                    context["team_outputs"][coder_type] = result

                    # Extract key artifacts for next coders
                    if coder_type == "database" and result.get("success"):
                        context["database_schema"] = result.get("output", "")
                    elif coder_type == "api" and result.get("success"):
                        context["api_contract"] = result.get("output", "")

                # Merge with current outputs
                current_outputs.update(iteration_outputs)

                # Step 3: Validate
                if log_callback:
                    await log_callback("\n🔍 Validating build quality...")

                validation = await self.validate_build(current_outputs, requirements)

                if log_callback:
                    await log_callback(f"   Score: {validation.score:.2%}")
                    await log_callback(f"   Status: {'✅ PASSED' if validation.passed else '❌ NEEDS IMPROVEMENT'}")
                    if validation.critical_errors:
                        await log_callback(f"   Critical Errors: {len(validation.critical_errors)}")
                    if validation.warnings:
                        await log_callback(f"   Warnings: {len(validation.warnings)}")

                iteration_duration = asyncio.get_event_loop().time() - iteration_start

                iterations.append(BuildIteration(
                    iteration_number=iteration,
                    coders_executed=[CoderSpecialty(step["coder"]) for step in execution_order],
                    outputs=iteration_outputs,
                    validation_result=validation,
                    improvements_made=validation.improvements,
                    duration=iteration_duration
                ))

                # Check if we've achieved target quality
                if validation.score >= self.target_quality_score and validation.passed:
                    if log_callback:
                        await log_callback(f"\n🎉 Build achieved target quality ({validation.score:.2%}) - Complete!")
                    break

                # If last iteration and still not passed, accept current state
                if iteration == self.max_iterations:
                    if log_callback:
                        await log_callback(f"\n⚠️  Max iterations reached. Final score: {validation.score:.2%}")
                    break

                # Otherwise, continue iteration
                if log_callback:
                    await log_callback(f"\n🔧 Preparing iteration {iteration + 1} with improvements...")

            # Step 4: Store learnings
            if log_callback:
                await log_callback("\n💾 Storing build learnings in memory...")

            await self._store_build_memory(user_prompt, requirements, iterations)

            # Step 5: Compile final result
            final_validation = iterations[-1].validation_result if iterations else None

            result = {
                "status": "completed",
                "user_prompt": user_prompt,
                "requirements": requirements,
                "iterations": len(iterations),
                "final_score": final_validation.score if final_validation else 0.0,
                "passed": final_validation.passed if final_validation else False,
                "outputs": current_outputs,
                "validation": {
                    "score": final_validation.score,
                    "issues": final_validation.issues,
                    "improvements": final_validation.improvements,
                    "critical_errors": final_validation.critical_errors,
                    "warnings": final_validation.warnings,
                    "feedback": final_validation.feedback
                } if final_validation else None,
                "build_summary": self._create_build_summary(current_outputs, final_validation),
                "all_iterations": [
                    {
                        "iteration": it.iteration_number,
                        "score": it.validation_result.score,
                        "duration": it.duration
                    }
                    for it in iterations
                ]
            }

            if log_callback:
                await log_callback("\n✨ Coding orchestration complete!")
                await log_callback(f"   Final Quality Score: {result['final_score']:.2%}")
                await log_callback(f"   Total Iterations: {result['iterations']}")

            logger.info(f"Build orchestration complete: {result['final_score']:.2%} quality")
            return result

        except Exception as e:
            logger.error(f"Error in build orchestration: {e}", exc_info=True)
            if log_callback:
                await log_callback(f"\n❌ Error: {str(e)}")
            return {
                "status": "failed",
                "error": str(e),
                "user_prompt": user_prompt
            }

    def _create_build_summary(
        self,
        outputs: Dict[str, Any],
        validation: Optional[ValidationResult]
    ) -> str:
        """Create a human-readable summary of the build."""
        lines = ["# Build Summary\n"]

        lines.append("## Components Built:")
        for coder, output in outputs.items():
            if isinstance(output, dict) and output.get("success"):
                lines.append(f"- ✅ {coder.upper()}")
            else:
                lines.append(f"- ❌ {coder.upper()} (failed)")

        if validation:
            lines.append(f"\n## Quality Score: {validation.score:.2%}")
            lines.append(f"## Status: {'PASSED' if validation.passed else 'NEEDS IMPROVEMENT'}")

            if validation.critical_errors:
                lines.append("\n## Critical Errors:")
                for error in validation.critical_errors:
                    lines.append(f"- {error}")

            if validation.warnings:
                lines.append("\n## Warnings:")
                for warning in validation.warnings[:5]:  # Limit to 5
                    lines.append(f"- {warning}")

        return "\n".join(lines)

    async def _store_build_memory(
        self,
        user_prompt: str,
        requirements: Dict[str, Any],
        iterations: List[BuildIteration]
    ):
        """Store build results in memory for future learning."""
        try:
            final_iteration = iterations[-1] if iterations else None
            if not final_iteration:
                return

            # Create memory document
            memory_doc = f"""Build Project: {requirements.get('project_name', 'unknown')}

User Request: {user_prompt}

Project Type: {requirements.get('project_type', 'unknown')}
Tech Stack: {json.dumps(requirements.get('tech_stack', {}), indent=2)}
Complexity: {requirements.get('complexity', 'unknown')}

Build Process:
- Iterations: {len(iterations)}
- Final Quality Score: {final_iteration.validation_result.score:.2%}
- Status: {'PASSED' if final_iteration.validation_result.passed else 'NEEDS IMPROVEMENT'}

Key Learnings:
{json.dumps(final_iteration.validation_result.improvements, indent=2)}

Issues Encountered:
{json.dumps(final_iteration.validation_result.issues[:10], indent=2)}  # Limit to top 10
"""

            # Store in vector memory
            self.vector_memory.remember(
                documents=[memory_doc],
                metadatas=[{
                    "type": "build",
                    "project_type": requirements.get("project_type", "unknown"),
                    "complexity": requirements.get("complexity", "unknown"),
                    "score": final_iteration.validation_result.score,
                    "iterations": len(iterations)
                }],
                agent_id=None  # Global memory
            )

            logger.info("Build learnings stored in memory")

        except Exception as e:
            logger.error(f"Error storing build memory: {e}")
