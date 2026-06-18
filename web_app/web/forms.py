"""Shared WTForms used across the dashboard web views."""

from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms import PasswordField
from wtforms.validators import DataRequired


class LoginForm(FlaskForm):
    username = StringField(u'Username', validators=[DataRequired()])
    password = PasswordField(u'Password', validators=[DataRequired()])
