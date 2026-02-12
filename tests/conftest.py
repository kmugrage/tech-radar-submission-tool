"""Shared test fixtures."""

import pytest

from app.models import BlipSubmission, Quadrant, Ring


@pytest.fixture
def empty_blip():
    return BlipSubmission()


@pytest.fixture
def populated_blip():
    """A fully-filled blip submission for integration tests."""
    return BlipSubmission(
        name="Terraform",
        ring=Ring.ADOPT,
        quadrant=Quadrant.PLATFORMS,
        description=(
            "Terraform has become the de facto standard for infrastructure as "
            "code across our engagements. Teams consistently report faster "
            "provisioning, better reproducibility, and fewer configuration "
            "drift issues when adopting Terraform."
        ),
        client_references=["Client Alpha - cloud migration", "Client Beta - platform rebuild"],
        submitter_name="Jane Smith",
        submitter_contact="jane.smith@thoughtworks.com",
        why_now="Multi-cloud adoption is accelerating and Terraform's provider ecosystem has matured significantly.",
        alternatives_considered=["Pulumi", "AWS CloudFormation"],
        strengths=["Provider ecosystem", "State management", "HCL readability"],
        weaknesses=["State file complexity", "Slow plans on large infra"],
    )


@pytest.fixture
def adopt_blip():
    """A blip with Ring.ADOPT and all adopt-specific evidence fields."""
    return BlipSubmission(
        name="Docker",
        ring=Ring.ADOPT,
        quadrant=Quadrant.PLATFORMS,
        description=(
            "Docker containers have become the standard packaging format for "
            "applications across our client engagements. Production outcomes "
            "include faster deployments and consistent environments."
        ),
        client_references=["Client X - containerized microservices", "Client Y - CI/CD pipeline"],
        weaknesses=["Image size management", "Security scanning overhead"],
    )
