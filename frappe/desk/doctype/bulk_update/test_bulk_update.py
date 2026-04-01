# Copyright (c) 2023, Frappe Technologies and Contributors
# See LICENSE

import time

import frappe
from frappe.core.doctype.doctype.test_doctype import new_doctype
from frappe.desk.doctype.bulk_update.bulk_update import apply_formula, submit_cancel_or_update_docs
from frappe.tests import IntegrationTestCase, timeout
from frappe.utils import flt


class TestBulkUpdate(IntegrationTestCase):
	@classmethod
	def setUpClass(cls) -> None:
		super().setUpClass()
		cls.doctype = new_doctype(is_submittable=1, custom=1).insert().name
		frappe.db.commit()
		for _ in range(50):
			frappe.new_doc(cls.doctype, some_fieldname=frappe.mock("name")).insert()

	@timeout()
	def wait_for_assertion(self, assertion):
		"""Wait till an assertion becomes True"""
		while True:
			if assertion():
				break
			time.sleep(0.2)

	def test_bulk_submit_in_background(self):
		unsubmitted = frappe.get_all(self.doctype, {"docstatus": 0}, limit=5, pluck="name")
		failed = submit_cancel_or_update_docs(self.doctype, unsubmitted, action="submit")
		self.assertEqual(failed, [])

		def check_docstatus(docs, status):
			frappe.db.rollback()
			matching_docs = frappe.get_all(
				self.doctype, {"docstatus": status, "name": ("in", docs)}, pluck="name"
			)
			return set(matching_docs) == set(docs)

		unsubmitted = frappe.get_all(self.doctype, {"docstatus": 0}, limit=20, pluck="name")
		submit_cancel_or_update_docs(self.doctype, unsubmitted, action="submit")

		self.wait_for_assertion(lambda: check_docstatus(unsubmitted, 1))

		submitted = frappe.get_all(self.doctype, {"docstatus": 1}, limit=20, pluck="name")
		submit_cancel_or_update_docs(self.doctype, submitted, action="cancel")
		self.wait_for_assertion(lambda: check_docstatus(submitted, 2))

	def test_formula_plain_numeric_value(self):
		"""Test plain numeric value updates"""
		doc = frappe.get_doc({"doctype": "User", "first_name": "Test", "enabled": 1})

		# Test integer
		result = apply_formula(doc, "enabled", "1")
		self.assertEqual(result, 1.0)

		# Test float
		result = apply_formula(doc, "enabled", "123.45")
		self.assertEqual(result, 123.45)

		# Test negative number
		result = apply_formula(doc, "enabled", "-50")
		self.assertEqual(result, -50.0)

	def test_formula_addition(self):
		"""Test addition formula"""
		doc = {"field1": 100}

		result = apply_formula(doc, "field1", "=+10")
		self.assertEqual(result, 110.0)

		result = apply_formula(doc, "field1", "=+0.5")
		self.assertEqual(result, 100.5)

		# Test with zero current value
		doc_zero = {"field1": 0}
		result = apply_formula(doc_zero, "field1", "=+50")
		self.assertEqual(result, 50.0)

	def test_formula_subtraction(self):
		"""Test subtraction formula"""
		doc = {"field1": 100}

		result = apply_formula(doc, "field1", "=-10")
		self.assertEqual(result, 90.0)

		result = apply_formula(doc, "field1", "=-150")
		self.assertEqual(result, -50.0)

	def test_formula_multiplication(self):
		"""Test multiplication formula"""
		doc = {"field1": 100}

		result = apply_formula(doc, "field1", "=*2")
		self.assertEqual(result, 200.0)

		# 10% increase
		result = apply_formula(doc, "field1", "=*1.1")
		self.assertAlmostEqual(result, 110.0, places=2)

		# Test with zero
		result = apply_formula(doc, "field1", "=*0")
		self.assertEqual(result, 0.0)

	def test_formula_division(self):
		"""Test division formula"""
		doc = {"field1": 100}

		result = apply_formula(doc, "field1", "=/2")
		self.assertEqual(result, 50.0)

		result = apply_formula(doc, "field1", "=/4")
		self.assertEqual(result, 25.0)

		# Test division by zero
		with self.assertRaises(frappe.ValidationError) as context:
			apply_formula(doc, "field1", "=/0")
		self.assertIn("Division by zero", str(context.exception))

	def test_formula_modulo(self):
		"""Test modulo formula"""
		doc = {"field1": 100}

		result = apply_formula(doc, "field1", "=%3")
		self.assertEqual(result, 1.0)

		result = apply_formula(doc, "field1", "=%7")
		self.assertEqual(result, 2.0)

		# Test modulo by zero
		with self.assertRaises(frappe.ValidationError) as context:
			apply_formula(doc, "field1", "=%0")
		self.assertIn("Modulo by zero", str(context.exception))

	def test_formula_complex_expressions(self):
		"""Test complex formulas with 'current' variable"""
		doc = {"field1": 100}

		# (current + 1000) * 1.05
		result = apply_formula(doc, "field1", "=(current+1000)*1.05")
		self.assertAlmostEqual(result, 1155.0, places=2)

		# current * 2 + 50
		result = apply_formula(doc, "field1", "=current*2+50")
		self.assertAlmostEqual(result, 250.0, places=2)

		# (current - 20) / 2
		result = apply_formula(doc, "field1", "=(current-20)/2")
		self.assertAlmostEqual(result, 40.0, places=2)

	def test_formula_invalid_inputs(self):
		"""Test error handling for invalid formulas"""
		doc = {"field1": 100}

		# Empty formula after =
		with self.assertRaises(frappe.ValidationError) as context:
			apply_formula(doc, "field1", "=")
		self.assertIn("Formula cannot be empty", str(context.exception))

		# Invalid operator
		with self.assertRaises(frappe.ValidationError) as context:
			apply_formula(doc, "field1", "=+abc")
		self.assertIn("Invalid formula", str(context.exception))

		# Invalid text input
		with self.assertRaises(frappe.ValidationError) as context:
			apply_formula(doc, "field1", "abc")
		self.assertIn("Invalid input", str(context.exception))

		# Invalid expression
		with self.assertRaises(frappe.ValidationError) as context:
			apply_formula(doc, "field1", "=(current++)")
		self.assertIn("Invalid formula", str(context.exception))

	def test_formula_non_string_inputs(self):
		"""Test that non-string inputs are returned as-is"""
		doc = {"field1": 100}

		# Integer input
		result = apply_formula(doc, "field1", 123)
		self.assertEqual(result, 123)

		# Float input
		result = apply_formula(doc, "field1", 45.67)
		self.assertEqual(result, 45.67)

		# None input
		result = apply_formula(doc, "field1", None)
		self.assertIsNone(result)

	def test_bulk_update_with_formula(self):
		"""Test bulk update with formula on multiple documents"""
		# Create test doctype with a numeric field
		test_dt = new_doctype(fields=[{"fieldname": "price", "fieldtype": "Currency"}], custom=1).insert()
		frappe.db.commit()

		# Create test documents
		docs = []
		for i in range(5):
			doc = frappe.new_doc(test_dt.name)
			doc.price = 100 + (i * 10)  # 100, 110, 120, 130, 140
			doc.insert()
			docs.append(doc.name)

		frappe.db.commit()

		# Apply 10% increase using formula
		failed = submit_cancel_or_update_docs(test_dt.name, docs, action="update", data={"price": "=*1.1"})
		self.assertEqual(failed, [])

		# Verify updates
		updated_docs = frappe.get_all(test_dt.name, filters={"name": ("in", docs)}, fields=["name", "price"])
		expected_prices = [110.0, 121.0, 132.0, 143.0, 154.0]

		for idx, updated_doc in enumerate(sorted(updated_docs, key=lambda x: x.name)):
			self.assertAlmostEqual(flt(updated_doc.price), expected_prices[idx], places=2)

		# Clean up
		for doc_name in docs:
			frappe.delete_doc(test_dt.name, doc_name)
		frappe.delete_doc("DocType", test_dt.name)

	def test_bulk_update_with_addition_formula(self):
		"""Test bulk update with addition formula"""
		# Create test doctype with a numeric field
		test_dt = new_doctype(fields=[{"fieldname": "quantity", "fieldtype": "Int"}], custom=1).insert()
		frappe.db.commit()

		# Create test documents
		docs = []
		for i in range(3):
			doc = frappe.new_doc(test_dt.name)
			doc.quantity = 50 + (i * 5)  # 50, 55, 60
			doc.insert()
			docs.append(doc.name)

		frappe.db.commit()

		# Add 100 to each document
		failed = submit_cancel_or_update_docs(test_dt.name, docs, action="update", data={"quantity": "=+100"})
		self.assertEqual(failed, [])

		# Verify updates
		updated_docs = frappe.get_all(test_dt.name, filters={"name": ("in", docs)}, fields=["name", "quantity"])
		expected_quantities = [150.0, 155.0, 160.0]

		for idx, updated_doc in enumerate(sorted(updated_docs, key=lambda x: x.name)):
			self.assertEqual(flt(updated_doc.quantity), expected_quantities[idx])

		# Clean up
		for doc_name in docs:
			frappe.delete_doc(test_dt.name, doc_name)
		frappe.delete_doc("DocType", test_dt.name)

	def test_formula_with_whitespace(self):
		"""Test formulas with extra whitespace"""
		doc = {"field1": 100}

		# Whitespace around formula
		result = apply_formula(doc, "field1", "  =+10  ")
		self.assertEqual(result, 110.0)

		# Whitespace in complex formula
		result = apply_formula(doc, "field1", "= ( current + 50 ) * 2")
		self.assertAlmostEqual(result, 300.0, places=2)
