from .zoos import zoos_bp
from .houses import houses_bp
from .zoo_species import zoo_species_bp
from .domains import domains_bp
from .locations import locations_bp
from .location_types import location_types_bp


def register_zoo_blueprints(app):
    app.register_blueprint(zoos_bp)
    app.register_blueprint(houses_bp)
    app.register_blueprint(zoo_species_bp)
    app.register_blueprint(domains_bp)
    app.register_blueprint(locations_bp)
    app.register_blueprint(location_types_bp)
