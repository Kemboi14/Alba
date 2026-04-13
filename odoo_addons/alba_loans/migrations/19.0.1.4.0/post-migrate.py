# -*- coding: utf-8 -*-
"""
post-migrate for alba_loans 19.0.1.4.0

Injects the Documents tab (loan_document_ids One2many field) into the
loan application form view after the models are fully loaded.

Why: The One2many field referencing alba.loan.document causes a circular
dependency error during XML view parsing on upgrade. By keeping the XML
view free of this field and injecting it via post-migrate, the upgrade
completes successfully and the Documents tab is restored afterwards.
"""
from odoo import api, SUPERUSER_ID

_MODULE = "alba_loans"


def _inject_documents_tab(env):
    """
    Inject the Documents tab (loan_document_ids) into the loan application
    form view. This is needed because the One2many field causes a circular
    dependency error during XML view parsing on upgrade.
    """
    view = env.ref(f"{_MODULE}.view_alba_loan_application_form", raise_if_not_found=False)
    if not view:
        return

    doc_arch = '''<field name="loan_document_ids" nolabel="1">
                                    <list string="Documents" editable="bottom">
                                        <field name="name" string="Document Name"/>
                                        <field name="document_type" string="Type"/>
                                        <field name="attachment_id"
                                               string="File"
                                               widget="many2one_binary"
                                               required="1"/>
                                        <field name="state"
                                               string="Status"
                                               widget="badge"
                                               decoration-success="state == 'verified'"
                                               decoration-warning="state == 'draft'"
                                               decoration-danger="state == 'rejected'"/>
                                        <field name="uploaded_by" string="Uploaded By" readonly="1"/>
                                        <field name="description" string="Notes" optional="hide"/>
                                    </list>
                                </field>'''

    current_arch = view.arch_db or view.arch
    # Replace empty Documents page with the full one
    placeholder = '<page string="Documents" name="documents">\n                            </page>'
    full_page = '<page string="Documents" name="documents">\n                                %s\n                            </page>' % doc_arch
    if placeholder in current_arch:
        new_arch = current_arch.replace(placeholder, full_page)
        view.sudo().write({"arch": new_arch, "arch_db": new_arch})


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Inject Documents tab into view (circular dependency workaround)
    _inject_documents_tab(env)
