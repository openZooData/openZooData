from .zoos import admin_zoos_bp
from .tenants import admin_tenants_bp
from .users import admin_users_bp
from .roles import admin_roles_bp
from .system import admin_system_bp
from .fixtures import admin_fixtures_bp


def register_admin_blueprints(app):
    app.register_blueprint(admin_zoos_bp)
    app.register_blueprint(admin_tenants_bp)
    app.register_blueprint(admin_users_bp)
    app.register_blueprint(admin_roles_bp)
    app.register_blueprint(admin_system_bp)
    app.register_blueprint(admin_fixtures_bp)
