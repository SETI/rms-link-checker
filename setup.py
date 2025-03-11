from setuptools import setup, find_packages

setup(
    name="check_links",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "requests>=2.25.0",
        "beautifulsoup4>=4.9.0",
        "colorama>=0.4.4",
    ],
    entry_points={
        "console_scripts": [
            "check_links=check_links.cli:main",
        ],
    },
    author="RMS Link Checker",
    author_email="example@example.com",
    description="A tool for checking broken links and cataloging internal assets on websites",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/check_links",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)