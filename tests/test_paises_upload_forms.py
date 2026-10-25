from datetime import date

from app import create_app
from app import db
from app.models import Archivo, Categoria, Comercio, Cuenta, Movimiento, Pais, Subcategoria, TipoCambio, User


def test_paises_add_and_edit_forms_use_multipart_upload():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})

    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(Pais(nombre='Argentina', codigo_iso='AR', logo_filename=None))
        db.session.commit()

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = '1'
                sess['_fresh'] = True

            add_page = client.get('/paises/add')
            edit_page = client.get('/paises/1/edit')

            assert 'enctype="multipart/form-data"' in add_page.get_data(as_text=True)
            assert 'enctype="multipart/form-data"' in edit_page.get_data(as_text=True)


def test_dashboard_subcategory_filter_does_not_crash():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})

    with app.app_context():
        db.drop_all()
        db.create_all()

        user = User(username='tester', password_hash='hash', role='user')
        db.session.add(user)
        db.session.commit()

        categoria = Categoria(nombre='Comida')
        db.session.add(categoria)
        db.session.commit()

        subcategoria = Subcategoria(nombre='Supermercado', categoria_id=categoria.id)
        db.session.add(subcategoria)
        db.session.commit()

        cuenta = Cuenta(
            banco='Banco',
            tipo_cuenta='Ahorro',
            numero_cuenta='123456',
            titular='Tester',
            moneda='GTQ',
            user_id=user.id,
        )
        db.session.add(cuenta)
        db.session.commit()

        archivo = Archivo(
            tipo_archivo='estado_cuenta',
            filename='test.csv',
            file_hash='abc123',
            user_id=user.id,
        )
        db.session.add(archivo)
        db.session.commit()

        comercio = Comercio(
            nombre='Mi comercio',
            categoria_id=categoria.id,
            subcategoria_id=subcategoria.id,
            tipo_contabilizacion='gastos',
        )
        db.session.add(comercio)
        db.session.commit()

        db.session.add(TipoCambio(moneda='GTQ', valor=1.0))
        db.session.add(
            Movimiento(
                fecha=date(2026, 9, 10),
                cuenta_id=cuenta.id,
                descripcion='Compra',
                monto=-100.0,
                moneda='GTQ',
                tipo='debito',
                archivo_id=archivo.id,
                user_id=user.id,
                comercio_id=comercio.id,
            )
        )
        db.session.commit()

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(user.id)
                sess['_fresh'] = True

            response = client.get(
                f'/dashboard?start_date=2026-01-01&end_date=2026-12-31&subcategoria_id={subcategoria.id}'
            )

            assert response.status_code == 200
            assert b'dashboard' in response.data.lower()
