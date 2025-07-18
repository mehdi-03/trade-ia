#!/usr/bin/env python3
"""
Script de configuration de l'environnement de développement.
Installe toutes les dépendances nécessaires pour le développement local.
"""

import os
import subprocess
import sys
from pathlib import Path


def run_command(command, cwd=None):
    """Exécute une commande et affiche le résultat."""
    print(f"Exécution: {command}")
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True
        )
        print(f"✅ Succès: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Erreur: {e.stderr}")
        return False


def setup_virtual_environment():
    """Configure l'environnement virtuel."""
    print("🔧 Configuration de l'environnement virtuel...")
    
    # Création de l'environnement virtuel
    if not run_command("python -m venv venv"):
        print("❌ Impossible de créer l'environnement virtuel")
        return False
    
    # Activation de l'environnement virtuel
    if os.name == 'nt':  # Windows
        activate_script = "venv\\Scripts\\activate"
    else:  # Linux/Mac
        activate_script = "source venv/bin/activate"
    
    print(f"✅ Environnement virtuel créé: {activate_script}")
    return True


def install_dependencies():
    """Installe les dépendances pour tous les services."""
    print("📦 Installation des dépendances...")
    
    services = [
        "services/data-ingestion",
        "services/ai-engine", 
        "services/order-executor"
    ]
    
    for service in services:
        requirements_file = f"{service}/requirements.txt"
        if os.path.exists(requirements_file):
            print(f"📦 Installation des dépendances pour {service}...")
            
            # Installation avec pip
            if not run_command(f"pip install -r {requirements_file}"):
                print(f"❌ Erreur lors de l'installation pour {service}")
                return False
    
    # Installation des outils de développement
    dev_packages = [
        "pytest",
        "pytest-asyncio", 
        "pytest-cov",
        "black",
        "flake8",
        "mypy",
        "pre-commit"
    ]
    
    print("🔧 Installation des outils de développement...")
    for package in dev_packages:
        if not run_command(f"pip install {package}"):
            print(f"❌ Erreur lors de l'installation de {package}")
            return False
    
    return True


def create_pyproject_toml():
    """Crée un fichier pyproject.toml pour la configuration du projet."""
    pyproject_content = """[tool.black]
line-length = 88
target-version = ['py311']
include = '\\.pyi?$'
extend-exclude = '''
/(
  # directories
  \\.eggs
  | \\.git
  | \\.hg
  | \\.mypy_cache
  | \\.tox
  | \\.venv
  | build
  | dist
)/
'''

[tool.flake8]
max-line-length = 88
extend-ignore = ["E203", "W503"]
exclude = [
    ".git",
    "__pycache__",
    "build",
    "dist",
    ".venv",
    "venv"
]

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
disallow_untyped_decorators = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
warn_unreachable = true
strict_equality = true

[[tool.mypy.overrides]]
module = [
    "aio_pika.*",
    "structlog.*",
    "tenacity.*",
    "prometheus_client.*"
]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = [
    "services/ai-engine/tests",
    "services/data-ingestion/tests", 
    "services/order-executor/tests"
]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
    "-v",
    "--tb=short",
    "--strict-markers",
    "--disable-warnings",
    "--asyncio-mode=auto"
]
markers = [
    "asyncio: marks tests as async",
    "integration: marks tests as integration tests",
    "unit: marks tests as unit tests",
    "slow: marks tests as slow running"
]
"""
    
    with open("pyproject.toml", "w") as f:
        f.write(pyproject_content)
    
    print("✅ Fichier pyproject.toml créé")


def main():
    """Fonction principale."""
    print("🚀 Configuration de l'environnement de développement")
    print("=" * 50)
    
    # Vérification de Python
    if sys.version_info < (3, 11):
        print("❌ Python 3.11+ requis")
        return False
    
    print(f"✅ Python {sys.version}")
    
    # Configuration de l'environnement virtuel
    if not setup_virtual_environment():
        return False
    
    # Installation des dépendances
    if not install_dependencies():
        return False
    
    # Création du fichier de configuration
    create_pyproject_toml()
    
    print("\n" + "=" * 50)
    print("✅ Environnement de développement configuré avec succès!")
    print("\n📋 Prochaines étapes:")
    print("1. Activez l'environnement virtuel:")
    if os.name == 'nt':
        print("   venv\\Scripts\\activate")
    else:
        print("   source venv/bin/activate")
    print("2. Lancez les tests: pytest")
    print("3. Formatez le code: black .")
    print("4. Vérifiez le code: flake8 .")
    print("5. Démarrez les services: docker-compose up -d")
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 
