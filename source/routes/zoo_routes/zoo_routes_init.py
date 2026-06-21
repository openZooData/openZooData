from .zoos import zoos_bp
from .houses import houses_bp
from .zoo_species import zoo_species_bp
from .domains import domains_bp
from .locations import locations_bp
from .location_types import location_types_bp
from .enclosures import enclosures_bp
from .species_global import species_bp
from .enclosure import enclosure_bp
from .enclosure_species import enclosure_species_bp
from .feeding_times import feeding_times_bp
from .births import births_bp

def register_zoo_blueprints(app):
    app.register_blueprint(zoos_bp)
    app.register_blueprint(houses_bp)
    app.register_blueprint(zoo_species_bp)
    app.register_blueprint(domains_bp)
    app.register_blueprint(locations_bp)
    app.register_blueprint(location_types_bp)
    app.register_blueprint(enclosures_bp)
    app.register_blueprint(species_bp)
    app.register_blueprint(enclosure_bp)
    app.register_blueprint(enclosure_species_bp)
    app.register_blueprint(feeding_times_bp)
    app.register_blueprint(births_bp)