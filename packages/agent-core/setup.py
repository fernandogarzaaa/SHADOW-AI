from setuptools import setup, find_packages

setup(
    name="agent-core",
    version="0.1.0",
    description="Core planning, policy, approvals, and device security for SHADOW-AI.",
    author="Fernando Garza",
    license="MIT",
    packages=find_packages(include=["agent_core", "agent_core.*"], exclude=["tests", "tests.*"]),
    install_requires=["pydantic>=2.10.0,<3"],
    python_requires=">=3.11",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
    ],
)
